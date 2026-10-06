"""In-memory fan-out of analytics invalidations to the admin SSE streams.

Deliberately kept separate from `app/core/realtime/`: this bus carries no
business data, has neither sequence numbering nor replay, and its ACL (admin)
is already enforced by the route dependency

Like the hub, it lives in process memory: keep UVICORN_WORKERS=1
as long as no shared broker exists.
"""

import asyncio
from datetime import UTC, datetime
from typing import Any

__all__ = ["AnalyticsEventBus", "analytics_bus"]

Invalidation = dict[str, Any]


class AnalyticsEventBus:
    def __init__(self) -> None:
        self._subscribers: set[asyncio.Queue[Invalidation]] = set()

    def subscribe(self) -> asyncio.Queue[Invalidation]:
        queue: asyncio.Queue[Invalidation] = asyncio.Queue(maxsize=1)
        self._subscribers.add(queue)
        return queue

    def unsubscribe(self, queue: asyncio.Queue[Invalidation]) -> None:
        self._subscribers.discard(queue)

    def publish(self, reason: str) -> int:
        """Invalidate the dashboards of all connected admins.

        Call after commit, from the event loop thread.
        Returns the number of notified streams.
        """
        payload: Invalidation = {
            "reason": reason,
            "at": datetime.now(UTC).isoformat(),
        }
        for queue in tuple(self._subscribers):
            if queue.full():
                try:
                    queue.get_nowait()
                except asyncio.QueueEmpty:
                    pass
            try:
                queue.put_nowait(payload)
            except asyncio.QueueFull:
                pass
        return len(self._subscribers)


analytics_bus = AnalyticsEventBus()
