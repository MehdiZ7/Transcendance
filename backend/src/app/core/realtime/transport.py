"""Everything below it (protocol, router, broker, session, registry) is pure
Python: no library, no I/O. `Connection` drives one socket through a
`Socket` port, so the WebSocket library stays an implementation detail.

Loop
----
Two coroutines share the session. The reader awaits client frames and hands
them to the session. The writer sleeps until the session signals that there
is work (a frame was queued, by a client frame or by an event the broker
delivered, or the session gapped), drains the session into the socket, then
checks the close conditions. Nothing is polled: an event published anywhere
reaches the socket as soon as the writer is scheduled.

Concurrency
-----------
Everything runs on the event loop thread. Broker, session and registry never
await, so each of their calls is atomic with respect to the other coroutines
and no lock is needed. The flip side: publish from the loop thread only.

Opening
-------
The first frame decides: `resume` reattaches through the registry, anything
else opens a new session and is then handled normally. A client that says
nothing at all is closed on the handshake timeout.

Closing
-------
Normal end, idle client, gapped session (queue overflowed, the stream has
holes), takeover and internal errors each get their own close code, so the
client knows whether to reconnect and resume, reconnect fresh, or give up.

Expiry
------
A connection can be given a `lifetime` (the seconds left on the credential
that opened it). Once spent, the socket is closed with POLICY_VIOLATION: the
client must authenticate again, which a logged-out browser cannot.

Takeover
--------
A `resume` can target a session still attached to another connection
(typically a half-open socket the server has not noticed yet). The registry
hands the session to the newcomer; the old connection sees that the session
epoch moved on, stops touching the session and closes its socket with
`REPLACED`. It never detaches or closes a session it no longer owns.

Native ping/pong belong to the library: this loop only sees the application
`ping`, which the session answers with `pong`.
"""

import asyncio
import logging
from typing import Protocol

from app.core.config import settings
from app.core.realtime.protocol import Resume, parse_client_frame
from app.core.realtime.registry import Registry, TooManySessions
from app.core.realtime.session import Session

__all__ = ["CloseCode", "ConnectionClosed", "Connection", "Socket"]

logger = logging.getLogger(__name__)

# Upper bound between two timer checks when nothing happens. Not a flush
# delay: frames are sent as soon as the session signals them.
DEFAULT_TICK = 1.0
DEFAULT_IDLE_TIMEOUT = settings.ws_session_ttl
DEFAULT_HANDSHAKE_TIMEOUT = settings.ws_handshake_timeout


class CloseCode:
    NORMAL = 1000
    GOING_AWAY = 1001
    POLICY_VIOLATION = 1008
    MESSAGE_TOO_BIG = 1009
    INTERNAL_ERROR = 1011
    TRY_AGAIN_LATER = 1013
    # Application range (4000-4999)
    REPLACED = 4000 # the session was resumed elsewhere: do not reconnect
    REAUTH = 4001 # closed server side (logout, suspension) or login expired


class ConnectionClosed(Exception):
    """Raised by the Socket port when the peer is gone."""


class Socket(Protocol):
    """The WebSocket, reduced to what this loop needs."""

    async def receive(self) -> str | bytes:
        """Wait for one text frame. Raises ConnectionClosed when the peer
        disconnects. Must be safe to cancel."""

    async def send(self, raw: str) -> None:
        """Send one text frame. Raises ConnectionClosed."""

    async def close(self, code: int, reason: str = "") -> None:
        """Close the socket. Must tolerate being called twice."""


class Connection:
    def __init__(
        self,
        socket: Socket,
        registry: Registry,
        principal: str,
        *,
        tick: float = DEFAULT_TICK,
        idle_timeout: float = DEFAULT_IDLE_TIMEOUT,
        handshake_timeout: float = DEFAULT_HANDSHAKE_TIMEOUT,
        lifetime: float | None = None,
    ) -> None:
        self._socket = socket
        self._registry = registry
        self._principal = principal
        self._tick = tick
        self._idle_timeout = idle_timeout
        self._handshake_timeout = handshake_timeout
        self._lifetime = lifetime
        self._deadline: float | None = None
        self.session: Session | None = None
        self._epoch: int | None = None
        self._wake = asyncio.Event()
        # Kept as one object so `unlisten` can recognize it
        self._notify = self._wake.set
        self._reader: asyncio.Task[None] | None = None

    async def run(self) -> int:
        """Serve this connection until it ends. Returns the close code."""
        if self._lifetime is not None:
            self._deadline = asyncio.get_running_loop().time() + self._lifetime
        try:
            if not await self.open():
                return await self._shutdown(CloseCode.POLICY_VIOLATION, "no handshake")
            code, reason = await self._serve()
            return await self._shutdown(code, reason)
        except TooManySessions:
            return await self._shutdown(CloseCode.TRY_AGAIN_LATER, "too many sessions")
        except ConnectionClosed:
            # Peer gone: keep the session in the registry so it can resume.
            self._detach()
            return CloseCode.GOING_AWAY
        except asyncio.CancelledError:
            # Server shutting down: same as a lost peer, then let it propagate.
            self._detach()
            raise
        except Exception:
            logger.exception("connection crashed")
            return await self._shutdown(CloseCode.INTERNAL_ERROR, "internal error")
        finally:
            await self._stop_reader()
            if self.session is not None:
                self.session.unlisten(self._notify)

    async def open(self) -> bool:
        try:
            async with asyncio.timeout(self._handshake_timeout):
                raw = await self._socket.receive()
        except TimeoutError:
            return False

        frame = parse_client_frame(raw)
        if isinstance(frame, Resume):
            self.session = self._registry.resume(
                frame.session, self._principal, frame.last_seq
            )
            self._epoch = self.session.epoch
        else:
            self.session = self._registry.start(self._principal)
            self._epoch = self.session.epoch
            self.session.handle(frame)
        self.session.listen(self._notify)
        await self._flush()
        return True

    async def _serve(self) -> tuple[int, str]:
        assert self.session is not None
        session = self.session
        self._reader = asyncio.create_task(self._read(session))
        while True:
            # Cleared before draining: whatever is queued during the sends
            # sets it again and the wait below returns at once.
            self._wake.clear()
            # Checked on both sides of the flush: the takeover can happen
            # while a send is in flight, and the queue is the newcomer's.
            if not self.owns_session:
                return CloseCode.REPLACED, "replaced"
            await self._flush()
            if not self.owns_session:
                return CloseCode.REPLACED, "replaced"

            if session.closed:
                # Closed server side: the client checks its login, then decides
                return CloseCode.REAUTH, "revoked"
            if self._reader.done():
                self._reader.result()  # re-raises ConnectionClosed or the crash
            if session.should_close:
                return CloseCode.TRY_AGAIN_LATER, "gap"
            remaining = self._idle_timeout - session.idle_for()
            if remaining <= 0:
                return CloseCode.GOING_AWAY, "idle"
            if self._deadline is not None:
                left = self._deadline - asyncio.get_running_loop().time()
                if left <= 0:
                    return CloseCode.REAUTH, "expired"
                remaining = min(remaining, left)

            try:
                async with asyncio.timeout(min(self._tick, remaining)):
                    await self._wake.wait()
            except TimeoutError:
                pass

    async def _read(self, session: Session) -> None:
        """Feed client frames to the session. Ends by raising, or quietly
        once the session was taken over: frames from this socket no longer
        concern it."""
        try:
            while True:
                raw = await self._socket.receive()
                if not self.owns_session or session.closed:
                    return
                session.handle(parse_client_frame(raw))
        finally:
            # Wake the writer so it sees the reader is done
            self._notify()

    async def _stop_reader(self) -> None:
        reader, self._reader = self._reader, None
        if reader is None:
            return
        reader.cancel()
        # Collects the reader's outcome, whatever it was
        await asyncio.gather(reader, return_exceptions=True)

    @property
    def owns_session(self) -> bool:
        """False once another connection resumed the session."""
        return self.session is not None and self.session.epoch == self._epoch

    async def _flush(self) -> None:
        assert self.session is not None
        for raw in self.session.drain_json():
            await self._socket.send(raw)

    async def _shutdown(self, code: int, reason: str) -> int:
        try:
            await self._socket.close(code, reason)
        except ConnectionClosed:
            pass
        self._detach()
        return code

    def _detach(self) -> None:
        if self.owns_session:
            assert self.session is not None
            self._registry.detach(self.session)

    async def close(self, code: int = CloseCode.NORMAL, reason: str = "") -> int:
        """Close the socket and end the session, unless it was taken over."""
        owned = self.owns_session
        code = await self._shutdown(code, reason)
        if owned:
            assert self.session is not None
            self._registry.close(self.session)
        return code
