"""Realtime endpoin: /api/ws

Mounted outside `/api/v1` because nginx proxies the upgrade on `location
/api/ws` only; a transport has no business API version anyway.

Only an authenticated browser gets a socket. Before `accept()`:

1. the `Origin` must be one of `settings.ws_allowed_origins_set`: the
   session cookie rides along with any page's handshake, so without this
   check another site could open a socket in the user's name (cross-site
   WebSocket hijacking). A missing `Origin` is refused too: the socket is
   for browsers;
2. the session cookie must decode, through the same code as the REST
   routes, to an active user.

Either refusal is a close before accept, which the client sees as an HTTP
403 on the handshake, with nothing else revealed. Once accepted, the socket
lives no longer than the JWT that opened it.
"""

import logging
import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, WebSocket
from starlette.websockets import WebSocketDisconnect

from app.core.config import settings
from app.core.db import async_session
from app.core.realtime.hub import Hub
from app.core.realtime.transport import CloseCode, Connection, ConnectionClosed
from app.core.security import load_active_user, session_claims_from_cookie
from app.models import User
from app.realtime import get_hub
from app.realtime_topics import connection_closed, connection_opened

__all__ = ["StarletteSocket", "WsIdentity", "authenticate_ws", "router"]

logger = logging.getLogger(__name__)
router = APIRouter()

UserLoader = Callable[[uuid.UUID], Awaitable[User | None]]

class StarletteSocket:
    """`Socket` port over a Starlette WebSocket."""

    def __init__(self, ws: WebSocket, *, max_bytes: int) -> None:
        self._ws = ws
        self._max_bytes = max_bytes

    async def receive(self) -> str | bytes:
        try:
            message = await self._ws.receive()
        except (WebSocketDisconnect, RuntimeError) as exc:
            raise ConnectionClosed() from exc
        if message["type"] == "websocket.disconnect":
            raise ConnectionClosed()
        text = message.get("text")
        raw: str | bytes = text if text is not None else message.get("bytes") or b""
        size = len(raw.encode()) if isinstance(raw, str) else len(raw)
        if size > self._max_bytes:
            await self.close(CloseCode.MESSAGE_TOO_BIG, "frame too big")
            raise ConnectionClosed()
        return raw

    async def send(self, raw: str) -> None:
        try:
            await self._ws.send_text(raw)
        except (WebSocketDisconnect, RuntimeError, OSError) as exc:
            raise ConnectionClosed() from exc

    async def close(self, code: int, reason: str = "") -> None:
        try:
            await self._ws.close(code, reason)
        except RuntimeError, OSError:
            pass

@dataclass(frozen=True)
class WsIdentity:
    principal: str
    expires_at: datetime

async def _load_user(public_id: uuid.UUID) -> User | None:
    async with async_session() as db:
        return await load_active_user(db, public_id)

def get_user_loader() -> UserLoader:
    return _load_user

def origin_allowed(origin: str | None) -> bool:
    if not origin:
        return False
    return origin.rstrip("/").lower() in settings.ws_allowed_origins_set

async def authenticate_ws(websocket: WebSocket, 
                        load_user: UserLoader = Depends(get_user_loader)) -> WsIdentity | None:
    origin = websocket.headers.get("origin")
    if not origin_allowed(origin):
        logger.warning("ws handshake refused: origin %r", origin)
        return None
    claims = session_claims_from_cookie(websocket)
    if claims is None:
        logger.info("ws handshake refused: no valid session cookie")
        return None 
    user = await load_user(claims.public_id)
    if user is None:
        logger.info("ws handshake refused: user %s inactive or gone", claims.public_id)
        return None
    return WsIdentity(str(user.public_id), claims.expires_at)

@router.websocket("/ws")
async def realtime(websocket: WebSocket,
                  identity: WsIdentity | None = Depends(authenticate_ws),
                  hub: Hub = Depends(get_hub)) -> None:
    if identity is None:
        await websocket.close(CloseCode.POLICY_VIOLATION)
        return
    await websocket.accept()
    lifetime = (identity.expires_at - datetime.now(UTC)).total_seconds()
    connection = Connection(
        StarletteSocket(websocket, max_bytes=settings.ws_max_frame_bytes),
        hub.registry,
        identity.principal,
        lifetime=lifetime,
    )
    connection_opened(hub, identity.principal)
    try:
        code = await connection.run()
    finally:
        connection_closed(hub, identity.principal)
    logger.debug("ws %s closed with %d", identity.principal, code)
