"""Integration tests: protocol + router + broker.

`FakeSession` stands in for the session module still to be written. It is
deliberately minimal — no queue, no replay buffer, no socket — but it wires
the three pieces exactly the way the real one will: parse, resolve, then
subscribe or publish, numbering what it enqueues.
"""

import json

import pytest

from app.core.realtime.broker import Broker
from app.core.realtime.protocol import (
    ClientMessage,
    ErrorFrame,
    EventFrame,
    Ping,
    PongFrame,
    Resume,
    SessionFrame,
    Subscribe,
    Unsubscribe,
    dump_server_frame,
    parse_client_frame,
    parse_server_frame,
)
from app.core.realtime.router import Router
from app.core.realtime.topics import Topic

CONVERSATION = Topic("conversation", "42")
FORBIDDEN = Topic("conversation", "99")
PRESENCE = Topic("presence")


class FakeSession:
    """Placeholder for session.py: assigns seq, applies client frames."""

    def __init__(
        self,
        broker: Broker,
        router: Router,
        principal: str = "alice",
        id: str = "s1",
    ) -> None:
        self._broker = broker
        self._router = router
        self.principal = principal
        self._id = id
        self._seq = 0
        self.outbox: list[object] = []

    @property
    def id(self) -> str:
        return self._id

    # ── Sink ──────────────────────────────────────────────────────

    def deliver(self, event: EventFrame) -> None:
        self._seq += 1
        self.outbox.append(event.with_seq(self._seq))

    # ── helpers ───────────────────────────────────────────────────

    def send(self, frame: object) -> None:
        self.outbox.append(frame)

    def close(self) -> None:
        self._broker.disconnect(self)

    @property
    def events(self) -> list[EventFrame]:
        return [f for f in self.outbox if isinstance(f, EventFrame)]

    @property
    def errors(self) -> list[ErrorFrame]:
        return [f for f in self.outbox if isinstance(f, ErrorFrame)]

    @property
    def last(self) -> object:
        return self.outbox[-1]

    # ── the loop transport.py will feed ───────────────────────────

    def handle(self, raw: str) -> None:
        frame = parse_client_frame(raw)

        if isinstance(frame, ErrorFrame):
            return self.send(frame)
        if isinstance(frame, Ping):
            return self.send(PongFrame())
        if isinstance(frame, Resume):
            return self.send(
                SessionFrame(session="tok", resumed=False, reason="new")
            )
        if isinstance(frame, (Subscribe, Unsubscribe)):
            return self._handle_subscription(frame)
        return self._handle_message(frame)

    def _handle_subscription(self, frame: Subscribe | Unsubscribe) -> None:
        topic = Topic.of(frame)

        if isinstance(frame, Unsubscribe):
            self._broker.unsubscribe(topic, self)
            return

        error = self._authorize(topic)
        if error is not None:
            return self.send(error)

        self._broker.subscribe(topic, self)
        hook = self._router.on_subscribe_for(topic)
        if hook is not None:
            for event in hook(self, topic):
                self.deliver(event)

    def _handle_message(self, frame: ClientMessage) -> None:
        handler = self._router.handler_for(frame.type)
        if handler is None:
            return self.send(
                ErrorFrame(
                    code="unknown_type",
                    topic_kind=frame.topic_kind,
                    topic_id=frame.topic_id,
                    ref=frame.ref,
                    detail=f"no handler for {frame.type}",
                )
            )

        error = self._authorize(Topic.of(frame))
        if error is not None:
            return self.send(error.model_copy(update={"ref": frame.ref}))

        handler(self, frame)

    def _authorize(self, topic: Topic) -> ErrorFrame | None:
        authorizer = self._router.authorizer_for(topic)
        if authorizer is None:
            return ErrorFrame(
                code="unknown_topic", topic_kind=topic.kind, topic_id=topic.id
            )
        if not authorizer(self.principal, topic):
            return ErrorFrame(
                code="forbidden", topic_kind=topic.kind, topic_id=topic.id
            )
        return None


# ── fixtures ──────────────────────────────────────────────────────


@pytest.fixture
def app_router(broker: Broker) -> Router:
    router = Router()

    @router.topic("conversation")
    def may_read(principal: str, topic: Topic) -> bool:
        return topic.id == "42"

    @router.topic("presence")
    def presence_is_public(principal: str, topic: Topic) -> bool:
        return True

    @router.on_subscribe("presence")
    def current_presence(session, topic: Topic):
        return [
            EventFrame(
                type="presence.snapshot",
                topic_kind=topic.kind,
                topic_id=topic.id,
                payload={"online": ["alice"]},
            )
        ]

    @router.message("message.create")
    def create_message(session: FakeSession, frame: ClientMessage) -> None:
        broker.publish(
            EventFrame(
                type="message.created",
                topic_kind=frame.topic_kind,
                topic_id=frame.topic_id,
                payload={"text": frame.payload["text"], "by": session.principal},
            )
        )

    router.check()
    router.freeze()
    return router


@pytest.fixture
def session(broker: Broker, app_router: Router) -> FakeSession:
    return FakeSession(broker, app_router, id="s1")


@pytest.fixture
def peer(broker: Broker, app_router: Router) -> FakeSession:
    return FakeSession(broker, app_router, principal="bob", id="s2")


def subscribe(topic: Topic) -> str:
    return json.dumps(
        {"type": "subscribe", "topic_kind": topic.kind, "topic_id": topic.id}
    )


def created(topic: Topic, text: str) -> EventFrame:
    return EventFrame(
        type="message.created",
        topic_kind=topic.kind,
        topic_id=topic.id,
        payload={"text": text},
    )


# ── subscribe, publish, deliver ───────────────────────────────────


def test_subscribe_then_receive(session: FakeSession, broker: Broker):
    session.handle(subscribe(CONVERSATION))

    broker.publish(created(CONVERSATION, "salut"))

    assert [e.type for e in session.events] == ["message.created"]
    assert session.events[0].payload == {"text": "salut"}


def test_session_numbers_what_it_delivers(session: FakeSession, broker: Broker):
    session.handle(subscribe(CONVERSATION))

    broker.publish(created(CONVERSATION, "un"))
    broker.publish(created(CONVERSATION, "deux"))

    assert [e.seq for e in session.events] == [1, 2]


def test_each_session_numbers_independently(
    session: FakeSession, peer: FakeSession, broker: Broker
):
    session.handle(subscribe(PRESENCE))  # peer joins one event later
    broker.publish(EventFrame(type="presence.join", topic_kind="presence"))
    peer.handle(subscribe(PRESENCE))
    broker.publish(EventFrame(type="presence.leave", topic_kind="presence"))

    assert [e.seq for e in session.events] == [1, 2, 3]  # snapshot + 2 events
    assert [e.seq for e in peer.events] == [1, 2]  # snapshot + 1 event


def test_unsubscribe_stops_delivery(session: FakeSession, broker: Broker):
    session.handle(subscribe(CONVERSATION))
    session.handle(
        json.dumps(
            {"type": "unsubscribe", "topic_kind": "conversation", "topic_id": "42"}
        )
    )

    broker.publish(created(CONVERSATION, "salut"))

    assert session.events == []


def test_close_removes_every_subscription(session: FakeSession, broker: Broker):
    session.handle(subscribe(CONVERSATION))
    session.handle(subscribe(PRESENCE))

    session.close()

    assert broker.topics(session) == frozenset()
    assert broker.publish(created(CONVERSATION, "salut")) == 0


def test_on_subscribe_sends_initial_state(session: FakeSession):
    session.handle(subscribe(PRESENCE))

    snapshot = session.events[0]
    assert snapshot.type == "presence.snapshot"
    assert snapshot.seq == 1


# ── authorization ─────────────────────────────────────────────────


def test_forbidden_topic_is_refused(session: FakeSession, broker: Broker):
    session.handle(subscribe(FORBIDDEN))

    assert session.errors[0].code == "forbidden"
    assert broker.publish(created(FORBIDDEN, "salut")) == 0


def test_unknown_topic_kind_is_refused(session: FakeSession):
    session.handle(subscribe(Topic("secret", "1")))

    assert session.errors[0].code == "unknown_topic"


def test_error_frame_carries_the_topic(session: FakeSession):
    session.handle(subscribe(FORBIDDEN))

    error = session.errors[0]
    assert (error.topic_kind, error.topic_id) == ("conversation", "99")


# ── client messages ───────────────────────────────────────────────


def test_client_message_reaches_subscribers(
    session: FakeSession, peer: FakeSession, broker: Broker
):
    session.handle(subscribe(CONVERSATION))
    peer.handle(subscribe(CONVERSATION))

    session.handle(
        json.dumps(
            {
                "type": "message.create",
                "topic_kind": "conversation",
                "topic_id": "42",
                "ref": "r1",
                "payload": {"text": "salut"},
            }
        )
    )

    for receiver in (session, peer):
        assert receiver.events[-1].type == "message.created"
        assert receiver.events[-1].payload == {"text": "salut", "by": "alice"}


def test_unknown_message_type_is_refused(session: FakeSession):
    session.handle(
        json.dumps(
            {
                "type": "message.explode",
                "topic_kind": "conversation",
                "topic_id": "42",
                "ref": "r7",
            }
        )
    )

    error = session.errors[0]
    assert error.code == "unknown_type"
    assert error.ref == "r7"


def test_forbidden_message_echoes_the_ref(session: FakeSession):
    session.handle(
        json.dumps(
            {
                "type": "message.create",
                "topic_kind": "conversation",
                "topic_id": "99",
                "ref": "r9",
                "payload": {"text": "nope"},
            }
        )
    )

    assert session.errors[0].code == "forbidden"
    assert session.errors[0].ref == "r9"


def test_publishing_does_not_require_being_subscribed(
    session: FakeSession, peer: FakeSession
):
    peer.handle(subscribe(CONVERSATION))

    session.handle(
        json.dumps(
            {
                "type": "message.create",
                "topic_kind": "conversation",
                "topic_id": "42",
                "payload": {"text": "salut"},
            }
        )
    )

    assert session.events == []
    assert len(peer.events) == 1


# ── control frames and bad input ──────────────────────────────────


def test_ping_is_answered_with_pong(session: FakeSession):
    session.handle('{"type": "ping"}')

    assert isinstance(session.last, PongFrame)


def test_resume_is_answered_with_a_session_frame(session: FakeSession):
    session.handle('{"type": "resume", "session": "tok", "last_seq": 417}')

    assert isinstance(session.last, SessionFrame)


@pytest.mark.parametrize(
    "raw",
    [
        pytest.param("not json", id="invalid-json"),
        pytest.param('{"type": "subscribe"}', id="missing-topic"),
        pytest.param('{"type": "ping", "extra": 1}', id="extra-field"),
    ],
)
def test_bad_input_yields_bad_request_and_changes_nothing(
    session: FakeSession, broker: Broker, raw: str
):
    session.handle(raw)

    assert session.errors[0].code == "bad_request"
    assert len(broker) == 0


# ── wire round trip ───────────────────────────────────────────────


def test_delivered_events_survive_the_wire(session: FakeSession, broker: Broker):
    session.handle(subscribe(CONVERSATION))
    broker.publish(created(CONVERSATION, "salut"))

    event = session.events[0]
    assert parse_server_frame(dump_server_frame(event)) == event


def test_delivered_event_matches_the_protocol_shape(
    session: FakeSession, broker: Broker
):
    session.handle(subscribe(CONVERSATION))
    broker.publish(created(CONVERSATION, "salut"))

    data = json.loads(dump_server_frame(session.events[0]))

    assert data == {
        "type": "message.created",
        "topic_kind": "conversation",
        "topic_id": "42",
        "payload": {"text": "salut"},
        "seq": 1,
        "ts": session.events[0].ts,
    }


def test_every_outgoing_frame_is_valid(session: FakeSession, broker: Broker):
    session.handle(subscribe(PRESENCE))
    session.handle(subscribe(FORBIDDEN))
    session.handle('{"type": "ping"}')
    session.handle("not json")
    broker.publish(EventFrame(type="presence.join", topic_kind="presence"))

    assert len(session.outbox) == 5
    for frame in session.outbox:
        assert parse_server_frame(dump_server_frame(frame)) == frame


def test_broker_isolation_between_topics(
    session: FakeSession, peer: FakeSession, broker: Broker
):
    session.handle(subscribe(CONVERSATION))
    peer.handle(subscribe(PRESENCE))

    broker.publish(created(CONVERSATION, "salut"))

    assert len(session.events) == 1
    assert [e.type for e in peer.events] == ["presence.snapshot"]