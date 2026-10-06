"""Dynamic registry"""

import logging
from typing import Protocol, runtime_checkable

from app.core.realtime.protocol import EventFrame
from app.core.realtime.topics import Topic

__all__ = ["Broker", "Sink"]

logger = logging.getLogger(__name__)


@runtime_checkable
class Sink(Protocol):
    """Anythin that can receive events."""

    @property
    def id(self) -> str:
        """Stable identifier"""

    def deliver(self, event: EventFrame) -> None:
        """Enqueue the event. Must not block, do I/O or raise"""


class Broker:
    def __init__(self) -> None:
        self._by_topic: dict[Topic, set[Sink]] = {}
        self._by_sink: dict[Sink, set[Topic]] = {}

    def subscribe(self, topic: Topic, sink: Sink) -> bool:
        subscribers = self._by_topic.setdefault(topic, set())
        if sink in subscribers:
            return False
        subscribers.add(sink)
        self._by_sink.setdefault(sink, set()).add(topic)
        return True

    def unsubscribe(self, topic: Topic, sink: Sink) -> bool:
        subscribers = self._by_topic.get(topic)
        if subscribers is None or sink not in subscribers:
            return False
        subscribers.discard(sink)
        if not subscribers:
            del self._by_topic[topic]
        topics = self._by_sink.get(sink)
        if topics is not None:
            topics.discard(topic)
            if not topics:
                del self._by_sink[sink]
        return True

    def disconnect(self, sink: Sink) -> None:
        for topic in self._by_sink.pop(sink, set()):
            subscribers = self._by_topic.get(topic)
            if subscribers is None:
                continue
            subscribers.discard(sink)
            if not subscribers:
                del self._by_topic[topic]

    def publish(self, event: EventFrame) -> int:
        """Deliver to every subscriber of the event's topic."""
        topic = Topic.of(event)
        subscribers = self._by_topic.get(topic)
        if not subscribers:
            return 0

        delivered = 0
        for sink in tuple(subscribers):
            try:
                sink.deliver(event)
            except Exception:
                logger.exception("sing %s failed on %s, dropping it", sink.id, topic)
                self.disconnect(sink)
            else:
                delivered += 1
        return delivered

    def subscribers(self, topic: Topic) -> frozenset[Sink]:
        return frozenset(self._by_topic.get(topic, ()))

    def topics(self, sink: Sink) -> frozenset[Topic]:
        return frozenset(self._by_sink.get(sink, ()))

    def active_topics(self) -> frozenset[Topic]:
        return frozenset(self._by_topic)

    def __len__(self) -> int:
        return len(self._by_sink)
