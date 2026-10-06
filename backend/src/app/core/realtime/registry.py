"""Table of live sessions, keyed by session token"""

import logging
import secrets
import time
from typing import Callable

from app.core.config import settings
from app.core.realtime.broker import Broker
from app.core.realtime.router import Router
from app.core.realtime.session import (
    DEFAULT_MAX_TOPICS,
    DEFAULT_QUEUE_LIMIT,
    DEFAULT_REPLAY_LIMIT,
    Limiter,
    Session,
)

__all__ = ["DEFAULT_MAX_SESSIONS", "DEFAULT_TTL", "Registry", "TooManySessions"]


logger = logging.getLogger(__name__)

DEFAULT_TTL = settings.ws_session_ttl
DEFAULT_MAX_SESSIONS = settings.ws_max_sessions_per_user

Clock = Callable[[], float]
TokenFactory = Callable[[], str]

class TooManySessions(RuntimeError):
    """Too many attached sessions"""


class Registry:
    def __init__(
        self,
        router: Router,
        broker: Broker,
        *,
        ttl: float = DEFAULT_TTL,
        clock: Clock = time.monotonic,
        queue_limit: int = DEFAULT_QUEUE_LIMIT,
        replay_limit: int = DEFAULT_REPLAY_LIMIT,
        limiter: Limiter | None = None,
        token_factory: TokenFactory = lambda: secrets.token_urlsafe(24),
        max_sessions: int = DEFAULT_MAX_SESSIONS,
        max_topics: int = DEFAULT_MAX_TOPICS,
    ) -> None:
        self._router = router
        self._broker = broker
        self._ttl = ttl
        self._clock = clock
        self._limiter = limiter
        self._queue_limit = queue_limit
        self._replay_limit = replay_limit
        self._token_factory = token_factory
        self._max_sessions = max_sessions
        self._max_topics = max_topics
        self._sessions: dict[str, Session] = {}

    def start(self, principal: str, *, reason: str = "new") -> Session:
        self._make_room(principal)
        session = self._new_session(principal)
        self._sessions[session.id] = session
        session.hello(reason)
        return session

    def _make_room(self, principal: str) -> None:
        """Keep the principal under `max_sessions`"""
        mine = [s for s in self.sessions_of(principal) if not s.closed]
        excess = len(mine) - self._max_sessions + 1
        if excess <= 0:
            return
        detached = sorted (
            (s for s in mine if not s.attached),
            key=lambda s: s.idle_for(),
            reverse=True,
        )
        if len(detached) < excess:
            logger.warning("%s holds %d sessions, refused", principal, len(mine))
            raise TooManySessions(principal)
        for session in detached[:excess]:
            logger.info("session %s evicted to make room", session.id)
            self.close(session)

    def resume(self, token: str, principal: str, last_seq: int) -> Session:
        session = self.get(token)
        if session is None:
            return self.start(principal, reason="expired")
        if session.principal != principal:
            logger.warning("session %s claimed by %s, refused", token, principal)
            return self.start(principal, reason="expired")
        if session.attached:
            logger.info("session %s taken over", token)
            session.detach()
        session.resume(last_seq)
        return session

    def _new_session(self, principal: str) -> Session:
        return Session(
            self._new_token(),
            principal,
            self._router,
            self._broker,
            queue_limit=self._queue_limit,
            replay_limit=self._replay_limit,
            clock=self._clock,
            limiter=self._limiter,
            max_topics= self._max_topics,
        )

    def _new_token(self) -> str:
        MAX_RETRY = 10
        for _ in range(MAX_RETRY):
            token = self._token_factory()
            if token not in self._sessions:
                return token
        raise RuntimeError("token factory keeps colliding")

    def get(self, token: str) -> Session | None:
        session = self._sessions.get(token)
        if session is None:
            return None
        if session.closed:
            self._evict(session)
            return None
        if self._expired(session):
            self._expire(session)
            return None
        return session

    def sessions_of(self, principal: str) -> tuple[Session, ...]:
        return tuple(s for s in self._sessions.values() if s.principal == principal)

    def _expired(self, session: Session) -> bool:
        return not session.attached and session.idle_for() > self._ttl

    def _expire(self, session: Session) -> None:
        logger.info("session %s expired after %.0fs", session.id, session.idle_for())
        session.close()
        self._evict(session)

    def _evict(self, session: Session) -> None:
        self._sessions.pop(session.id, None)

    def sweep(self) -> int:
        doomed = [s for s in self._sessions.values() if s.closed or self._expired(s)]
        for session in doomed:
            if not session.closed:
                self._expire(session)
            else:
                self._evict(session)
        return len(doomed)

    # Connection lifecycle
    def detach(self, session: Session) -> None:
        session.detach()

    def close(self, session: Session) -> None:
        session.close()
        self._evict(session)

    def close_all(self) -> None:
        for session in list(self._sessions.values()):
            session.close()
        self._sessions.clear()

    def tokens(self) -> frozenset[str]:
        return frozenset(self._sessions)

    def sessions(self) -> tuple[Session, ...]:
        return tuple(self._sessions.values())

    def __contains__(self, token: object) -> bool:
        return isinstance(token, str) and self.get(token) is not None

    def __len__(self) -> int:
        return len(self._sessions)

    def close_principal(self, principal: str) -> int:
        """Close every session of `principal` (logout, suspension)
        Attached connections hang up with REAUTH."""
        sessions = self.sessions_of(principal)
        for session in sessions:
            self.close(session)
        return len(sessions)
