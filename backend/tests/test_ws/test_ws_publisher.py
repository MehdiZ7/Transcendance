"""Unit tests for publisher.py: the entry point business code uses."""

import pytest
from pydantic import ValidationError

from app.core.realtime.broker import Broker
from conftest import RecordingSink
from app.core.realtime.protocol import EventFrame
from app.core.realtime.publisher import LocalBackend, NullBackend, Publisher, local_publisher
from app.core.realtime.topics import Topic

CONVERSATION = Topic("conversation", "42")
PRESENCE = Topic("presence")


class RecordingBackend:
    def __init__(self) -> None:
        self.published: list[EventFrame] = []

    def publish(self, event: EventFrame) -> int:
        self.published.append(event)
        return 1


class BrokenBackend:
    def publish(self, event: EventFrame) -> int:
        raise RuntimeError("redis is down")


@pytest.fixture
def backend() -> RecordingBackend:
    return RecordingBackend()


@pytest.fixture
def publisher(backend: RecordingBackend) -> Publisher:
    return Publisher(backend)



def test_publish_builds_the_event(publisher: Publisher, backend: RecordingBackend):
    publisher.publish("message.created", CONVERSATION, {"text": "salut"})

    event = backend.published[0]
    assert event.type == "message.created"
    assert (event.topic_kind, event.topic_id) == ("conversation", "42")
    assert event.payload == {"text": "salut"}


def test_payload_defaults_to_empty(publisher: Publisher, backend: RecordingBackend):
    publisher.publish("presence.join", PRESENCE)

    assert backend.published[0].payload == {}


def test_published_events_carry_no_seq(
    publisher: Publisher, backend: RecordingBackend
):
    """Numbering is the session's job."""
    publisher.publish("message.created", CONVERSATION)

    assert backend.published[0].seq is None


def test_events_are_timestamped(publisher: Publisher, backend: RecordingBackend):
    publisher.publish("message.created", CONVERSATION)

    assert backend.published[0].ts


def test_topic_without_id(publisher: Publisher, backend: RecordingBackend):
    publisher.publish("presence.join", PRESENCE)

    assert backend.published[0].topic_id is None




@pytest.mark.parametrize("reserved", ["session", "error", "pong"])
def test_reserved_types_are_rejected(publisher: Publisher, reserved: str):
    with pytest.raises(ValidationError, match="reserved"):
        publisher.publish(reserved, CONVERSATION)


def test_empty_type_is_rejected(publisher: Publisher):
    with pytest.raises(ValidationError):
        publisher.publish("", CONVERSATION)


def test_preset_seq_is_rejected(publisher: Publisher):
    event = EventFrame(type="message.created", topic_kind="conversation").with_seq(3)

    with pytest.raises(ValueError, match="seq"):
        publisher.publish_event(event)




def test_publish_returns_the_delivery_count(publisher: Publisher):
    assert publisher.publish("message.created", CONVERSATION) == 1


def test_backend_failure_never_reaches_the_caller():
    publisher = Publisher(BrokenBackend())

    assert publisher.publish("message.created", CONVERSATION) == 0


def test_unserializable_payload_is_refused_before_reaching_the_backend(
    publisher: Publisher, backend: RecordingBackend
):
    # would otherwise pass publish() and crash every subscriber's writer
    assert publisher.publish("message.created", CONVERSATION, {"x": object()}) == 0
    assert backend.published == []


def test_json_native_payload_types_are_accepted(publisher: Publisher, backend: RecordingBackend):
    payload = {"n": 1, "s": "a", "b": True, "none": None, "list": [1, 2], "nested": {"k": "v"}}

    assert publisher.publish("message.created", CONVERSATION, payload) == 1
    assert backend.published[0].payload == payload


def test_null_backend_drops_everything():
    publisher = Publisher(NullBackend())

    assert publisher.publish("message.created", CONVERSATION) == 0


def test_publish_event_passes_the_frame_through(
    publisher: Publisher, backend: RecordingBackend
):
    event = EventFrame(type="message.created", topic_kind="conversation", ts="fixed")

    publisher.publish_event(event)

    assert backend.published[0] is event




def test_local_backend_delivers_to_subscribers(
    broker: Broker, sink: RecordingSink, other_sink: RecordingSink
):
    publisher = local_publisher(broker)
    broker.subscribe(CONVERSATION, sink)
    broker.subscribe(CONVERSATION, other_sink)

    delivered = publisher.publish("message.created", CONVERSATION, {"text": "salut"})

    assert delivered == 2
    assert sink.received[0].payload == {"text": "salut"}


def test_local_backend_without_subscribers(broker: Broker):
    assert local_publisher(broker).publish("message.created", CONVERSATION) == 0


def test_local_backend_respects_topics(broker: Broker, sink: RecordingSink):
    publisher = Publisher(LocalBackend(broker))
    broker.subscribe(PRESENCE, sink)

    publisher.publish("message.created", CONVERSATION)

    assert sink.received == []


def test_business_code_never_sees_the_broker(broker: Broker, sink: RecordingSink):
    """The whole point: a call site only knows a type, a topic and a payload."""
    publisher = local_publisher(broker)
    broker.subscribe(CONVERSATION, sink)

    def create_message(text: str) -> None:  # stands for application code
        publisher.publish("message.created", CONVERSATION, {"text": text})

    create_message("salut")

    assert sink.types == ["message.created"]