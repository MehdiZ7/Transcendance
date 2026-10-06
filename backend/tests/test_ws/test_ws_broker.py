"""Tests for the dynamic registry (broker.py).

No socket, no asyncio, no sleep: the broker is synchronous, so every
assertion is deterministic.
"""

import pytest

from app.core.realtime.broker import Broker
from app.core.realtime.protocol import EventFrame
from conftest import ExplodingSink, RecordingSink, SelfRemovingSink
from app.core.realtime.topics import Topic

CONVERSATION = Topic("conversation", "42")
OTHER = Topic("conversation", "43")
PRESENCE = Topic("presence")


def event(topic: Topic = CONVERSATION, type_: str = "message.created") -> EventFrame:
    return EventFrame(type=type_, topic_kind=topic.kind, topic_id=topic.id)


# ── subscribe / unsubscribe ───────────────────────────────────────


def test_subscribe_registers_both_ways(broker: Broker, sink: RecordingSink):
    assert broker.subscribe(CONVERSATION, sink) is True

    assert broker.subscribers(CONVERSATION) == {sink}
    assert broker.topics(sink) == {CONVERSATION}


def test_subscribe_is_idempotent(broker: Broker, sink: RecordingSink):
    broker.subscribe(CONVERSATION, sink)

    assert broker.subscribe(CONVERSATION, sink) is False
    assert broker.subscribers(CONVERSATION) == {sink}
    assert broker.publish(event()) == 1


def test_unsubscribe_removes_both_ways(broker: Broker, sink: RecordingSink):
    broker.subscribe(CONVERSATION, sink)

    assert broker.unsubscribe(CONVERSATION, sink) is True
    assert broker.subscribers(CONVERSATION) == frozenset()
    assert broker.topics(sink) == frozenset()


def test_unsubscribe_unknown_is_a_noop(broker: Broker, sink: RecordingSink):
    assert broker.unsubscribe(CONVERSATION, sink) is False

    broker.subscribe(CONVERSATION, sink)
    assert broker.unsubscribe(PRESENCE, sink) is False
    assert broker.topics(sink) == {CONVERSATION}


def test_unsubscribe_leaves_other_subscribers(
    broker: Broker, sink: RecordingSink, other_sink: RecordingSink
):
    broker.subscribe(CONVERSATION, sink)
    broker.subscribe(CONVERSATION, other_sink)

    broker.unsubscribe(CONVERSATION, sink)

    assert broker.subscribers(CONVERSATION) == {other_sink}


def test_topics_with_the_same_kind_are_distinct(broker: Broker, sink: RecordingSink):
    broker.subscribe(CONVERSATION, sink)

    assert broker.subscribers(OTHER) == frozenset()
    assert broker.publish(event(OTHER)) == 0


# ── no leaks ──────────────────────────────────────────────────────


def test_empty_topic_is_dropped(broker: Broker, sink: RecordingSink):
    broker.subscribe(CONVERSATION, sink)
    broker.unsubscribe(CONVERSATION, sink)

    assert broker.active_topics() == frozenset()
    assert len(broker) == 0


def test_disconnect_clears_every_topic(
    broker: Broker, sink: RecordingSink, other_sink: RecordingSink
):
    broker.subscribe(CONVERSATION, sink)
    broker.subscribe(PRESENCE, sink)
    broker.subscribe(PRESENCE, other_sink)

    broker.disconnect(sink)

    assert broker.topics(sink) == frozenset()
    assert broker.active_topics() == {PRESENCE}
    assert broker.subscribers(PRESENCE) == {other_sink}
    assert len(broker) == 1


def test_disconnect_is_idempotent(broker: Broker, sink: RecordingSink):
    broker.subscribe(CONVERSATION, sink)
    broker.disconnect(sink)
    broker.disconnect(sink)

    assert len(broker) == 0


def test_disconnect_of_unknown_sink_is_a_noop(broker: Broker, sink: RecordingSink):
    broker.disconnect(sink)

    assert len(broker) == 0


# ── publish ───────────────────────────────────────────────────────


def test_publish_delivers_to_subscribers(
    broker: Broker, sink: RecordingSink, other_sink: RecordingSink
):
    broker.subscribe(CONVERSATION, sink)
    broker.subscribe(CONVERSATION, other_sink)
    published = event()

    assert broker.publish(published) == 2
    assert sink.received == [published]
    assert other_sink.received == [published]


def test_publish_without_subscriber(broker: Broker):
    assert broker.publish(event()) == 0


def test_publish_does_not_leak_across_topics(
    broker: Broker, sink: RecordingSink, other_sink: RecordingSink
):
    broker.subscribe(CONVERSATION, sink)
    broker.subscribe(PRESENCE, other_sink)

    broker.publish(event(CONVERSATION))

    assert len(sink.received) == 1
    assert other_sink.received == []


def test_publish_ignores_type_when_routing(broker: Broker, sink: RecordingSink):
    broker.subscribe(CONVERSATION, sink)

    broker.publish(event(type_="message.created"))
    broker.publish(event(type_="message.deleted"))

    assert sink.types == ["message.created", "message.deleted"]


def test_published_events_carry_no_seq(broker: Broker, sink: RecordingSink):
    """Numbering belongs to the session, not to the broker."""
    broker.subscribe(CONVERSATION, sink)

    broker.publish(event())

    assert sink.received[0].seq is None


def test_topic_without_id_is_its_own_topic(broker: Broker, sink: RecordingSink):
    """(kind, None) and (kind, "1") are two different topics."""
    broker.subscribe(PRESENCE, sink)

    assert broker.publish(event(PRESENCE)) == 1
    assert broker.publish(event(Topic("presence", "1"))) == 0


# ── robustness ────────────────────────────────────────────────────


def test_broken_sink_does_not_stop_the_others(broker: Broker):
    broken = ExplodingSink("broken")
    healthy = RecordingSink("healthy")
    broker.subscribe(CONVERSATION, broken)
    broker.subscribe(CONVERSATION, healthy)

    delivered = broker.publish(event())

    assert delivered == 1
    assert len(healthy.received) == 1


def test_broken_sink_is_dropped(broker: Broker):
    broken = ExplodingSink("broken")
    broker.subscribe(CONVERSATION, broken)

    broker.publish(event())

    assert broker.subscribers(CONVERSATION) == frozenset()
    assert broker.topics(broken) == frozenset()
    assert broker.publish(event()) == 0


def test_unsubscribe_from_inside_deliver(broker: Broker):
    leaving = SelfRemovingSink("leaving", broker)
    staying = RecordingSink("staying")
    broker.subscribe(CONVERSATION, leaving)
    broker.subscribe(CONVERSATION, staying)

    assert broker.publish(event()) == 2

    assert broker.subscribers(CONVERSATION) == {staying}
    assert broker.publish(event()) == 1
    assert len(leaving.received) == 1
    assert len(staying.received) == 2


# ── introspection ─────────────────────────────────────────────────


def test_introspection_returns_immutable_copies(broker: Broker, sink: RecordingSink):
    broker.subscribe(CONVERSATION, sink)

    subscribers = broker.subscribers(CONVERSATION)
    topics = broker.topics(sink)

    assert isinstance(subscribers, frozenset)
    assert isinstance(topics, frozenset)
    with pytest.raises(AttributeError):
        subscribers.add(RecordingSink("s3"))  # type: ignore[attr-defined]


def test_brokers_do_not_share_state(sink: RecordingSink):
    a, b = Broker(), Broker()
    a.subscribe(CONVERSATION, sink)

    assert b.subscribers(CONVERSATION) == frozenset()
    assert b.publish(event()) == 0