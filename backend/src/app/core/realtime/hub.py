"""Process-wide assembly of the realtime stack, started and stopped bu the application lifespan"""

import asyncio
import contextlib
import logging
from typing import Any


from app.core.config import settings
from app.core.realtime.broker import Broker
from app.core.realtime.limiter import WindowLimiter
from app.core.realtime.publisher import Publisher, local_publisher
from app.core.realtime.registry import Registry
from app.core.realtime.router import Router
from app.core.realtime.session import Limiter

__all__ = ["RATE_WINDOW", "Hub"]

logger = logging.getLogger(__name__)

RATE_WINDOW = 10.0


def default_limiter() -> Limiter | None:
    """The limiter from the settings; None (no limit) when set to 0"""
    limit = settings.ws_rate_limit_per_10s
    return WindowLimiter(limit, RATE_WINDOW) if limit > 0 else None

class Hub:
    """Router + broker + publisher + registry + the sweeper task"""
    def __init__(self, router: Router, *, limiter: Limiter | None = None,
                 sweep_every: float = settings.ws_session_ttl,
                 **registry_options: Any) -> None:
        self.router = router
        self.broker = Broker()
        self.publisher : Publisher = local_publisher(self.broker)
        self.limiter = limiter or default_limiter()
        self.registry = Registry(router, self.broker, limiter=self.limiter, **registry_options)
        self._sweep_every = sweep_every
        self._sweeper : asyncio.Task[None] | None = None

    async def start(self) -> None:
        """Check and freeze the router, start sweeping expired sessions."""
        self.router.check()
        self.router.freeze()
        if self._sweeper is None:
            self._sweeper = asyncio.create_task(self._sweep())

    async def stop(self) -> None:
        sweeper, self._sweeper = self._sweeper, None
        if sweeper is not None:
            sweeper.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await sweeper
        self.registry.close_all()

    async def _sweep(self) -> None:
        while True:
            await asyncio.sleep(self._sweep_every)
            self.sweep()

    def sweep(self) -> int:
        swept = self.registry.sweep()
        if isinstance(self.limiter, WindowLimiter):
            self.limiter.forget_idle()
        if swept:
            logger.info("swept %d realtime session(s)", swept)
        return swept