"""Rate limit for inbound client frames."""

import time
from collections import deque
from collections.abc import Callable

__all__ = ["WindowLimiter"]

Clock = Callable[[], float]

class WindowLimiter:
    """Sliding window per principal, shared by all of its tabs."""

    def __init__(self, limit: int, window: float, *,
                  clock: Clock = time.monotonic) -> None:
        if limit < 1 or window <= 0:
            raise ValueError("limit must be >= 1 and window > 0")
        self._limit = limit
        self._window = window
        self._clock = clock
        self._hits : dict[str, deque[float]] = {}

    def __call__(self, principal: str, frame: object) -> bool:
        now = self._clock()
        hits = self._hits.setdefault(principal, deque())
        while hits and now - hits[0] >= self._window:
            hits.popleft()
        if len(hits) >= self._limit:
            return False
        hits.append(now)
        return True

    def forget_idle(self) -> int:
        """Drops principals with no hit left in the window. Called by the sweeper."""
        now = self._clock()
        idle = [
            p for p, hits in self._hits.items()
            if not hits or now - hits[-1] >= self._window
        ]
        for principal in idle:
            del self._hits[principal]
        return len(idle)