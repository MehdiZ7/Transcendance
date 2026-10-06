"""realtime entry point for business code."""

import logging
from typing import Protocol

from app.core.realtime.broker import Broker
from app.core.realtime.protocol import EventFrame
from app.core.realtime.topics import Topic

__all__ = ["Backend", "LocalBackend", "NullBackend", "Publisher", "local_publisher"]

logger = logging.getLogger(__name__)


class Backend(Protocol):
    """Where published events go. Swap this, keep every call site."""

    def publish(self, event: EventFrame) -> int:
        """Return how many local sinks received the event."""


class LocalBackend:
    """Single-process: straight to the in-memory broker."""

    def __init__(self, broker: Broker) -> None:
        self._broker = broker

    def publish(self, event: EventFrame) -> int:
        return self._broker.publish(event)


class NullBackend:
    """Drops everything. For tests and for code paths where realtime is off."""

    def publish(self, event: EventFrame) -> int:
        return 0


class Publisher:
    """Call it from the event loop thread only (async route, background
    task): the broker and the sessions are not thread-safe. Code running in
    a worker thread must go through `loop.call_soon_threadsafe`."""

    def __init__(self, backend: Backend) -> None:
        self._backend = backend

    def publish(
        self,
        type: str,
        topic: Topic,
        payload: dict | None = None,
    ) -> int:
        """Build the event and hand it to the backend."""
        event = EventFrame(
            type=type,
            topic_kind=topic.kind,
            topic_id=topic.id,
            payload=payload or {},
        )
        return self.publish_event(event)

    def publish_event(self, event: EventFrame) -> int:
        """Publish an already built event"""
        if event.seq is not None:
            raise ValueError("seq is assigned by the session, not by the publisher")
        try:
            # Same dump the writers do later: a payload that fails here would
            # crash every subscriber's socket and stay in the replay buffer
            event.model_dump_json(exclude_none=True)
            return self._backend.publish(event)
        except Exception:
            logger.exception("publishing %s on %s failed", event.type, event.topic_kind)
            return 0


def local_publisher(broker: Broker) -> Publisher:
    """Shortcut for the single-process setup."""
    return Publisher(LocalBackend(broker))
