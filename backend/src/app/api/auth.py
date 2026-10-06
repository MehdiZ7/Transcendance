import logging
import secrets
from datetime import UTC, datetime
from urllib.parse import quote, unquote, urlencode, urlsplit

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload
from starlette.responses import RedirectResponse

from app.core.config import settings
from app.core.db import get_session
from app.core.oauth42 import FtOAuthClient, FtProfile, OAuthLoginError, get_ft_client
from app.core.passwords import hash_password, verify_password
from app.core.ratelimit import limit_password_attempts
from app.core.realtime.hub import Hub
from app.core.security import (
    SessionClaims,
    clear_session_cookie,
    create_session_token,
    get_current_user,
    session_claims_from_cookie,
    set_session_cookie,
)
from app.core.serializers import to_current_user
from app.models import OAuthAccount, User
from app.realtime import get_hub
from app.schemas.auth import (
    ChangePasswordRequest,
    CurrentUser,
    PasswordLoginRequest,
    RegisterRequest,
)

logger = logging.getLogger(__name__)
router = APIRouter()

PROVIDER = "42"
# /api/auth/* only (the 42 routes below, and the password routes, which ignore
# it): the state cookie is never sent to /api/v1 or to the front.
STATE_COOKIE_PATH = "/api/auth/"
NEXT_MAX_LENGTH = 512


def _safe_next(next_: str | None) -> str | None:
    """A path on this site to land on after login, or None.
    Anything a browser could read as another host is refused: "//host",
    "/\\host" (\\ is read as /), and tabs/newlines (stripped by browsers, so
    "/\\t/host" is "//host"). /api/ is refused too: not a page."""
    if not next_ or len(next_) > NEXT_MAX_LENGTH:
        return None
    if not next_.startswith("/") or next_.startswith("//") or "\\" in next_:
        return None
    if any(ord(c) < 0x20 or ord(c) == 0x7F for c in next_):
        return None
    parts = urlsplit(next_)
    if parts.scheme or parts.netloc or parts.path.startswith("/api/"):
        return None
    return next_


def _set_flow_cookie(response: Response, name: str, value: str) -> None:
    """The cookies living for one login, from /auth/login to its callback."""
    response.set_cookie(
        name,
        value,
        max_age=settings.oauth_state_max_age,
        httponly=True,
        samesite="lax",
        secure=settings.cookie_secure,
        path=STATE_COOKIE_PATH,
    )


def _clear_flow_cookie(response: Response, name: str) -> None:
    response.delete_cookie(
        name,
        httponly=True,
        samesite="lax",
        secure=settings.cookie_secure,
        path=STATE_COOKIE_PATH,
    )


def _set_state_cookie(response: Response, state: str) -> None:
    _set_flow_cookie(response, settings.oauth_state_cookie_name, state)


def _set_next_cookie(response: Response, next_: str | None) -> None:
    safe = _safe_next(next_)
    if safe is None:
        # a next left over from an abandoned login must not apply to this one
        _clear_flow_cookie(response, settings.oauth_next_cookie_name)
    else:
        # quoted: ? & ; have no place raw in a cookie value
        _set_flow_cookie(response, settings.oauth_next_cookie_name, quote(safe, safe=""))


def _next_from_cookie(request: Request) -> str | None:
    """Checked again: the cookie comes back from the browser, it can be forged."""
    return _safe_next(unquote(request.cookies.get(settings.oauth_next_cookie_name, "")))


def _redirect_to_app(error: str | None = None, next_: str | None = None) -> RedirectResponse:
    """Where every callback ends, success or not.
    The callback is a browser navigation, so a JSON 4xx would be shown raw:
    failures land on the app with ?auth_error=<code>
    instead 303 so the browser follows with a GET whatever it sent
    next_ only on success: after a failure the page asked for would bounce
    back to the login anyway.
    The state and next cookies are single-use either way."""
    if error is None:
        url = next_ or settings.post_login_redirect
    else:
        url = settings.post_login_redirect
        url += ("&" if "?" in url else "?") + urlencode({"auth_error": error})
    response = RedirectResponse(url, status_code=303)
    _clear_flow_cookie(response, settings.oauth_state_cookie_name)
    _clear_flow_cookie(response, settings.oauth_next_cookie_name)
    return response


def _ensure_usable(user: User) -> None:
    """A session for a deactivated or soft-deleted user gets 401"""
    if not user.is_active or user.deleted_at is not None:
        raise OAuthLoginError("account_disabled", f"user {user.public_id} is disabled")


async def _find_account(
    session: AsyncSession, provider_account_id: str
) -> OAuthAccount | None:
    return await session.scalar(
        select(OAuthAccount)
        .where(
            OAuthAccount.provider == PROVIDER,
            OAuthAccount.provider_account_id == provider_account_id,
        )
        .options(joinedload(OAuthAccount.user))
    )


async def _upsert_ft_user(session: AsyncSession, profile: FtProfile) -> User:
    """Resolve the 42 profile to a local user, creating one if needed.

    Identity is the numeric intra id stored in oauth_accounts, never the login:
    a 42 login can be renamed, the id cannot. display_name and avatar_path are
    seeded at creation (the avatar also filled while empty) and never
    overwritten: both are the user's to change in the app. email is refreshed
    on every login: it is not editable here and the intra is its source.
    """
    account = await _find_account(session, str(profile.id))
    if account is not None:
        user = account.user
        _ensure_usable(user)
        user.email = profile.email
        if user.avatar_path is None:
            user.avatar_path = profile.avatar_url
        return user

    user = await session.scalar(select(User).where(User.email == profile.email))
    if user is not None:
        if user.password_hash is not None:
            # A real local account owns this email: linking to it on email match
            # alone, with no proof of ownership, would hand the 42 login into
            # someone else's password-protected account.
            raise OAuthLoginError(
                "email_taken", f"{profile.email} belongs to a local account"
            )
        _ensure_usable(user)
        if user.avatar_path is None:
            user.avatar_path = profile.avatar_url
    else:
        user = User(
            email=profile.email,
            display_name=profile.login,
            avatar_path=profile.avatar_url,
            password_hash=None,
            email_verified_at=datetime.now(UTC),
        )
        session.add(user)

    session.add(
        OAuthAccount(provider=PROVIDER, provider_account_id=str(profile.id), user=user)
    )
    await session.flush()
    return user


@router.get("/auth/login")
async def login(
    next_: str | None = Query(None, alias="next"),
    client: FtOAuthClient = Depends(get_ft_client),
) -> RedirectResponse:
    if not settings.ft_client_id or not settings.ft_client_secret:
        # Redirecting anyway would only send the user to an intra error page.
        raise HTTPException(status_code=503, detail="42 login is not configured")
    state = secrets.token_urlsafe(32)
    response = RedirectResponse(client.authorize_url(state), status_code=307)
    _set_state_cookie(response, state)
    _set_next_cookie(response, next_)
    return response


@router.get("/auth/callback")
async def callback(
    request: Request,
    code: str | None = Query(None),
    state: str | None = Query(None),
    error: str | None = Query(None),
    client: FtOAuthClient = Depends(get_ft_client),
    session: AsyncSession = Depends(get_session),
) -> RedirectResponse:
    if error is not None:
        # The user declined on the intra, or the intra refused us: nothing to verify.
        logger.info("42 login declined by the intra: %s", error)
        return _redirect_to_app(error="denied")

    expected_state = request.cookies.get(settings.oauth_state_cookie_name)
    # compare_digest, not ==, so a mismatch cannot be probed byte by byte. On
    # bytes: the str form raises TypeError on non-ASCII input, which would
    # turn a forged state into a 500.
    if (
        not state
        or not expected_state
        or not secrets.compare_digest(state.encode(), expected_state.encode())
    ):
        logger.warning("42 login rejected: state mismatch")
        return _redirect_to_app(error="invalid_state")
    if not code:
        return _redirect_to_app(error="invalid_code")

    try:
        access_token = await client.exchange_code(code)
        profile = await client.fetch_profile(access_token)
        try:
            user = await _upsert_ft_user(session, profile)
            await session.commit()
        except IntegrityError:
            # Either a concurrent callback for the same profile won the race to
            # create the account, or the email refresh collided with another
            # row. Either way the account this profile maps to should now
            # exist (possibly with its pre-collision email) - re-fetch it
            # instead of failing the login outright.
            await session.rollback()
            account = await _find_account(session, str(profile.id))
            if account is None:
                raise OAuthLoginError(
                    "conflict", f"no account for 42 id {profile.id} after a collision"
                ) from None
            logger.warning(
                "42 login for id %s hit a collision, reusing its account", profile.id
            )
            user = account.user
            _ensure_usable(user)
    except OAuthLoginError as exc:
        logger.warning("42 login failed (%s): %s", exc.code, exc)
        return _redirect_to_app(error=exc.code)

    logger.info("42 login: user %s", user.public_id)
    response = _redirect_to_app(next_=_next_from_cookie(request))
    set_session_cookie(response, create_session_token(user.public_id))
    return response


@router.post("/auth/logout", status_code=204)
async def logout(
    request: Request,
    response: Response,
    hub: Hub = Depends(get_hub)
) -> None:
    claims = session_claims_from_cookie(request)
    if claims is not None:
        # The JWT is stateless: this closes the user's sockets on every device
        # Those still logged in check /users/me and come back
        hub.registry.close_principal(str(claims.public_id))
    clear_session_cookie(response)


def _open_session(response: Response, user: User) -> CurrentUser:
    set_session_cookie(response, create_session_token(user.public_id))
    return to_current_user(user)


def _is_fresh(claims: SessionClaims | None) -> bool:
    """The session was opened by a login of minutes ago."""
    if claims is None or claims.issued_at is None:
        return False
    age = (datetime.now(UTC) - claims.issued_at).total_seconds()
    return age <= settings.password_reauth_max_age


@router.post("/auth/register", status_code=201)
async def register(
    payload: RegisterRequest,
    response: Response,
    session: AsyncSession = Depends(get_session),
) -> CurrentUser:
    domain = payload.email.rpartition("@")[2]  # EmailStr lowercases the domain
    if domain in settings.register_blocked_email_domains_set:
        # Its owner signs in with 42. Nothing proves the address yet, so a
        # local account on it would only lock them out (email_taken above).
        raise HTTPException(status_code=403, detail="This address signs in with 42")
    # CITEXT: case-insensitive. Checked before hashing, so a duplicate costs
    # no hash; the unique constraint below settles a race.
    if await session.scalar(select(User.id).where(User.email == payload.email)):
        raise HTTPException(status_code=409, detail="Email already registered")

    user = User(
        email=payload.email,
        display_name=payload.display_name,
        password_hash=await hash_password(payload.password),
        # Set once a mail confirms the address: nothing proves it yet
        email_verified_at=None,
    )
    session.add(user)
    try:
        await session.commit()
    except IntegrityError:
        # two concurrent registers for the same email: one wins, this one gets 409
        await session.rollback()
        raise HTTPException(status_code=409, detail="Email already registered") from None

    logger.info("password register: user %s", user.public_id)
    return _open_session(response, user)


@router.post("/auth/login")
async def password_login(
    payload: PasswordLoginRequest,
    response: Response,
    session: AsyncSession = Depends(get_session),
) -> CurrentUser:
    limit_password_attempts(payload.email)
    user = await session.scalar(select(User).where(User.email == payload.email))
    # Unknown email, 42-only account and wrong password: one answer, after the
    # same argon2 work, so neither the status nor the timing tells which
    # emails have an account.
    valid = await verify_password(payload.password, user.password_hash if user else None)
    if user is None or not valid:
        raise HTTPException(status_code=401, detail="Invalid email or password")
    if not user.is_active or user.deleted_at is not None:
        # only told to someone who knows the password
        raise HTTPException(status_code=403, detail="Account disabled")

    logger.info("password login: user %s", user.public_id)
    return _open_session(response, user)


@router.post("/auth/password", status_code=204)
async def change_password(
    payload: ChangePasswordRequest,
    request: Request,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> None:
    if current_user.password_hash is None:
        # A 42 account has no password to prove, so the proof is a 42 login of
        # minutes ago. Without it, anyone at a computer left logged in could
        # add a password and keep the account after its owner logs out.
        if not _is_fresh(session_claims_from_cookie(request)):
            raise HTTPException(
                status_code=403, detail="Sign in with 42 again to set a password"
            )
    else:
        limit_password_attempts(current_user.email)
        if not payload.current_password or not await verify_password(
            payload.current_password, current_user.password_hash
        ):
            raise HTTPException(status_code=400, detail="Current password is incorrect")

    current_user.password_hash = await hash_password(payload.new_password)
    current_user.updated_at = datetime.now(UTC)
    await session.commit()
    logger.info("password updated: user %s", current_user.public_id)
