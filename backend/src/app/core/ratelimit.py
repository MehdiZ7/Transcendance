"""Rate limiting of the REST routes, per logged-in user.

Quotas (app/core/quotas.py) cap what is stored; this caps how fast a user can
ask. Two layers, both answering 429 with a `Retry-After` header:

- every request of a logged-in user, in two buckets: reads (`GET`) and writes
  (everything else), from `app/api/v1/__init__.py`;
- a stricter bucket on the routes that create something a person will see
  (messages, listings, reports, friend requests), on the route itself.

The user is read from the session cookie without a database lookup (the JWT is
verified, nothing more), so a refused request costs almost nothing, and it
runs before the route's own authentication: an invalid cookie is not limited
here, the route answers 401. Requests without a session are not limited here
either; per-IP limits are nginx's job (`limit_req`). The one exception is the
password check, limited per email tried (`limit_password_attempts`).

A limit of 0 disables the bucket (same convention as `ws_rate_limit_per_10s`).
State is in the memory of the process, like the websocket registry: one worker.
The dependencies are `async` on purpose: FastAPI would run a plain `def` in a
thread, and the counters are only safe from the event loop.
"""

import math
import time
from collections import deque
from collections.abc import Awaitable, Callable

from fastapi import HTTPException, Request

from app.core.config import settings
from app.core.security import session_claims_from_cookie

MINUTE = 60.0
HOUR = 3600.0
SAFE_METHODS = frozenset({"GET", "HEAD", "OPTIONS"})


class SlidingWindow:
    """`limit` hits per `window` seconds per key. Not thread-safe: called
    from the event loop only."""

    def __init__(self, clock: Callable[[], float] = time.monotonic) -> None:
        self._clock = clock
        self._hits: dict[tuple[str, str], tuple[float, deque[float]]] = {}
        self._last_sweep = clock()

    def hit(self, key: tuple[str, str], limit: int, window: float) -> float | None:
        """Count one request. None if it is allowed, else the seconds to wait."""
        now = self._clock()
        self._sweep(now)
        _, hits = self._hits.setdefault(key, (window, deque()))
        while hits and now - hits[0] >= window:
            hits.popleft()
        if len(hits) >= limit:
            return window - (now - hits[0])
        hits.append(now)
        return None

    def _sweep(self, now: float) -> None:
        """Forget keys with nothing left in their window, once a minute, so the
        table does not keep every user that ever made a request."""
        if now - self._last_sweep < MINUTE:
            return
        self._last_sweep = now
        idle = [k for k, (w, hits) in self._hits.items() if not hits or now - hits[-1] >= w]
        for key in idle:
            del self._hits[key]

    def clear(self) -> None:
        self._hits.clear()

    def __len__(self) -> int:
        return len(self._hits)


limiter = SlidingWindow()


def _hit(key: tuple[str, str], limit: int, window: float) -> None:
    if limit <= 0:
        return
    wait = limiter.hit(key, limit, window)
    if wait is not None:
        raise HTTPException(
            status_code=429,
            detail="Too many requests, slow down",
            headers={"Retry-After": str(max(1, math.ceil(wait)))},
        )


def _enforce(request: Request, bucket: str, limit: int, window: float) -> None:
    claims = session_claims_from_cookie(request)
    if claims is not None:
        _hit((bucket, str(claims.public_id)), limit, window)


def limit_password_attempts(email: str) -> None:
    """Password checks (login, change), keyed by the account's email rather
    than the client: nginx limits each IP, this caps guessing one account's
    password from many IPs. Called from the route, where the email is known."""
    _hit(("password", email.lower()), settings.rate_password_attempts_per_hour, HOUR)


def rate_limit(bucket: str, setting: str, window: float) -> Callable[[Request], Awaitable[None]]:
    """A route dependency: `setting` (a `rate_*` field of Settings) hits per
    `window` seconds for this user. Read at each request, so a test or a
    restart with another value takes effect."""

    async def dependency(request: Request) -> None:
        _enforce(request, bucket, getattr(settings, setting), window)

    return dependency


async def limit_requests(request: Request) -> None:
    """Every request of a logged-in user: one bucket for reads, one for writes."""
    if request.method in SAFE_METHODS:
        _enforce(request, "reads", settings.rate_reads_per_minute, MINUTE)
    else:
        _enforce(request, "writes", settings.rate_writes_per_minute, MINUTE)


limit_messages = rate_limit("messages", "rate_messages_per_minute", MINUTE)
limit_listings = rate_limit("listings", "rate_listings_per_hour", HOUR)
limit_reports = rate_limit("reports", "rate_reports_per_hour", HOUR)
limit_friend_requests = rate_limit("friend_requests", "rate_friend_requests_per_hour", HOUR)
limit_uploads = rate_limit("uploads", "rate_uploads_per_hour", HOUR)
