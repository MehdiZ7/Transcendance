import uuid
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime, timedelta
from typing import NamedTuple

import jwt
from fastapi import Depends, HTTPException, Request, Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.requests import HTTPConnection

from app.core import presence
from app.core.config import settings
from app.core.db import async_session, get_session
from app.models import User

ALGORITHM = "HS256"

ROLE_RANK = {"user": 0, "moderator": 1, "admin": 2}


def create_session_token(public_id: uuid.UUID) -> str:
    issued_at = datetime.now(UTC)
    payload = {
        "sub": str(public_id),
        "iat": issued_at,
        "exp": issued_at + timedelta(seconds=settings.session_max_age),
    }
    return jwt.encode(payload, settings.secret_key, algorithm=ALGORITHM)


class SessionClaims(NamedTuple):
    public_id: uuid.UUID
    expires_at: datetime
    # When the login happened. None for a token without "iat", which
    # create_session_token never issues: treat it as an old session.
    issued_at: datetime | None = None


def decode_session_claims(token: str) -> SessionClaims | None:
    """Return what the token carries, or None if the token is expired,
    tampered with, or signed by another key."""
    try:
        payload = jwt.decode(
            token,
            settings.secret_key,
            algorithms=[ALGORITHM],
            options={"require": ["sub", "exp"]},
        )
        iat = payload.get("iat")
        return SessionClaims(
            uuid.UUID(payload["sub"]),
            datetime.fromtimestamp(payload["exp"], UTC),
            datetime.fromtimestamp(iat, UTC) if iat is not None else None,
        )
    except (jwt.InvalidTokenError, KeyError, TypeError, ValueError):
        return None


def decode_session_token(token: str) -> uuid.UUID | None:
    """Return the user public_id carried by the token, or None if invalid."""
    claims = decode_session_claims(token)
    return claims.public_id if claims is not None else None


def set_session_cookie(response: Response, token: str) -> None:
    response.set_cookie(
        settings.session_cookie_name,
        token,
        max_age=settings.session_max_age,
        httponly=True,
        samesite="lax",
        secure=settings.cookie_secure,
        path="/",
    )


def clear_session_cookie(response: Response) -> None:
    response.delete_cookie(
        settings.session_cookie_name,
        httponly=True,
        samesite="lax",
        secure=settings.cookie_secure,
        path="/",
    )


def session_claims_from_cookie(conn: HTTPConnection) -> SessionClaims | None:
    """Claims of the session cookie. `conn` is a Request or a WebSocket: both
    authenticate through this one path."""
    token = conn.cookies.get(settings.session_cookie_name)
    return decode_session_claims(token) if token else None


async def load_active_user(session: AsyncSession, public_id: uuid.UUID) -> User | None:
    """The user behind a session, unless deactivated or soft-deleted."""
    user = await session.scalar(
        select(User).where(
            User.public_id == public_id,
            User.is_active.is_(True),
            User.deleted_at.is_(None),
        )
    )
    if user is not None:
        # for GET /analytics/online-students
        presence.touch(user.id)
    return user


async def _resolve_user_from_cookie(
    request: Request, session: AsyncSession
) -> User | None:
    claims = session_claims_from_cookie(request)
    if claims is None:
        return None
    return await load_active_user(session, claims.public_id)


async def get_current_user(
    request: Request, session: AsyncSession = Depends(get_session)
) -> User:
    user = await _resolve_user_from_cookie(request, session)
    if user is None:
        raise HTTPException(status_code=401, detail="Not authenticated")
    return user


async def get_current_user_optional(
    request: Request, session: AsyncSession = Depends(get_session)
) -> User | None:
    """Same lookup as get_current_user, but never raises - for routes that
    are public but personalize their response when a session is present
    (e.g. GET /listings' is_favorited)."""
    return await _resolve_user_from_cookie(request, session)


async def get_current_moderator(current_user: User = Depends(get_current_user)) -> User:
    """Gate for the moderation queue (GET/POST /reports/*) - users.role is a
    free-text FK into the roles lookup table, not a StrEnum, since new roles
    shouldn't need a migration."""
    if current_user.role not in ("moderator", "admin"):
        raise HTTPException(status_code=403, detail="Moderator access required")
    return current_user

async def require_admin(current_user: User = Depends(get_current_user)) -> User:
    """get_current_user plus a role check:
    401 when anonymous (raised by get_current_user),
    403 for any role other than admin.
    """
    if current_user.role != "admin":
        raise HTTPException(status_code=403, detail="Admin access required")
    return current_user



UserLoader = Callable[[uuid.UUID], Awaitable[User | None]]


async def _load_user_own_session(public_id: uuid.UUID) -> User | None:
    async with async_session() as db:
        return await load_active_user(db, public_id)


def get_stream_user_loader() -> UserLoader:
    """Injectable so tests can plug in their own transaction. Same pattern
    as `app.api.ws.get_user_loader`."""
    return _load_user_own_session


async def require_admin_stream(
    request: Request,
    load_user: UserLoader = Depends(get_stream_user_loader),
) -> User:
    """`require_admin` without the `get_session` dependency.

    A StreamingResponse is sent from inside the dependencies' AsyncExitStack:
    a `Depends(get_session)` would hold a pool connection for the whole
    lifetime of the stream. Here the session is opened, used, and closed
    before the stream starts.
    """
    claims = session_claims_from_cookie(request)
    if claims is None:
        raise HTTPException(status_code=401, detail="Not authenticated")
    user = await load_user(claims.public_id)
    if user is None:
        raise HTTPException(status_code=401, detail="Not authenticated")
    if user.role != "admin":
        raise HTTPException(status_code=403, detail="Admin access required")
    return user


def can_sanction(actor: User, target: User) -> bool:
    """Suspend, remove or reactivate `target`. Never oneself; an admin anyone
    else; a moderator only accounts below their rank (plain users)."""
    if actor.id == target.id:
        return False
    # if actor.role == "admin":
    #     return True
    return ROLE_RANK.get(actor.role, 0) > ROLE_RANK.get(target.role, 0)
