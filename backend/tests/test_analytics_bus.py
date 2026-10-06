"""Tests for the analytics invalidation bus (core/analytics_bus.py).

No socket, no asyncio, no sleep: the bus is synchronous, so every
assertion is deterministic. `asyncio.Queue` can be built and used through
its `*_nowait` methods outside of any event loop.
"""

import asyncio

import pytest

from app.core.analytics_bus import AnalyticsEventBus, analytics_bus


@pytest.fixture
def bus() -> AnalyticsEventBus:
    """Fresh instance: never the `analytics_bus` singleton, whose state
    would leak from one test to the next."""
    return AnalyticsEventBus()


# broadcast


def test_publish_reaches_every_subscriber(bus: AnalyticsEventBus):
    a, b = bus.subscribe(), bus.subscribe()

    assert bus.publish("listing.created") == 2

    assert a.get_nowait()["reason"] == "listing.created"
    assert b.get_nowait()["reason"] == "listing.created"


def test_publish_without_subscriber_is_a_noop(bus: AnalyticsEventBus):
    assert bus.publish("listing.created") == 0


# coalescing


def test_publish_coalesces_for_a_slow_subscriber(bus: AnalyticsEventBus):
    """A subscriber that doesn't read keeps the LATEST invalidation
    instead of silently losing one."""
    queue = bus.subscribe()

    bus.publish("listing.created")
    bus.publish("report.created")

    assert queue.qsize() == 1
    assert queue.get_nowait()["reason"] == "report.created"


def test_a_slow_subscriber_does_not_block_the_others(bus: AnalyticsEventBus):
    """The real risk of a fan-out: one frozen admin tab stalling the
    others. `put_nowait` never blocks, but nothing tested it."""
    slow, fast = bus.subscribe(), bus.subscribe()
    bus.publish("listing.created")  # fills `slow`, never read

    bus.publish("report.created")

    assert fast.qsize() == 1
    assert slow.get_nowait()["reason"] == "report.created"


# lifecycle


def test_unsubscribe_stops_delivery(bus: AnalyticsEventBus):
    queue = bus.subscribe()
    bus.unsubscribe(queue)

    assert bus.publish("listing.created") == 0
    with pytest.raises(asyncio.QueueEmpty):
        queue.get_nowait()


def test_unsubscribe_is_idempotent(bus: AnalyticsEventBus):
    """`discard`, not `remove`: the SSE generator's `finally` can run
    twice without raising."""
    queue = bus.subscribe()
    bus.unsubscribe(queue)
    bus.unsubscribe(queue)


def test_each_subscriber_gets_its_own_queue(bus: AnalyticsEventBus):
    a, b = bus.subscribe(), bus.subscribe()
    assert a is not b

    bus.publish("listing.created")
    a.get_nowait()

    assert b.qsize() == 1  # reading from one doesn't drain the other


# payload


def test_payload_carries_reason_and_timestamp(bus: AnalyticsEventBus):
    from datetime import datetime

    queue = bus.subscribe()
    bus.publish("report.resolved")

    payload = queue.get_nowait()
    assert payload["reason"] == "report.resolved"
    assert datetime.fromisoformat(payload["at"]).tzinfo is not None


def test_the_module_exposes_a_singleton():
    """The SSE generator subscribes to it; the routes publish to it."""
    assert isinstance(analytics_bus, AnalyticsEventBus)
