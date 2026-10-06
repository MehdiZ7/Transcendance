"""Unit tests for the session JWT helpers shared by REST and WebSocket."""

import uuid
from datetime import UTC, datetime, timedelta

import jwt
from starlette.requests import Request

from app.core.config import settings
from app.core.security import (
    ALGORITHM,
    create_session_token,
    decode_session_claims,
    decode_session_token,
    load_active_user,
    session_claims_from_cookie,
)


def sign(payload: dict, key: str | None = None) -> str:
    return jwt.encode(payload, key or settings.secret_key, algorithm=ALGORITHM)


def test_claims_carry_the_user_and_the_expiry():
    public_id = uuid.uuid4()
    before = datetime.now(UTC).replace(microsecond=0)

    claims = decode_session_claims(create_session_token(public_id))

    assert claims is not None
    assert claims.public_id == public_id
    expected = before + timedelta(seconds=settings.session_max_age)
    assert expected <= claims.expires_at <= expected + timedelta(seconds=2)
    assert claims.expires_at.tzinfo is UTC


def test_decode_session_token_still_returns_the_public_id():
    public_id = uuid.uuid4()

    assert decode_session_token(create_session_token(public_id)) == public_id


def test_expired_token_has_no_claims():
    token = sign({"sub": str(uuid.uuid4()), "exp": datetime.now(UTC) - timedelta(1)})

    assert decode_session_claims(token) is None


def test_token_without_exp_or_sub_has_no_claims():
    assert decode_session_claims(sign({"sub": str(uuid.uuid4())})) is None
    exp = datetime.now(UTC) + timedelta(hours=1)
    assert decode_session_claims(sign({"exp": exp})) is None


def test_token_with_a_malformed_sub_has_no_claims():
    exp = datetime.now(UTC) + timedelta(hours=1)

    assert decode_session_claims(sign({"sub": "not-a-uuid", "exp": exp})) is None
    assert decode_session_claims(sign({"sub": 42, "exp": exp})) is None


def test_token_signed_with_another_key_has_no_claims():
    exp = datetime.now(UTC) + timedelta(hours=1)
    token = sign({"sub": str(uuid.uuid4()), "exp": exp}, key="x" * 32)

    assert decode_session_claims(token) is None


def test_garbage_has_no_claims():
    assert decode_session_claims("not.a.jwt") is None
    assert decode_session_claims("") is None


def _request(cookie: str | None) -> Request:
    headers = [] if cookie is None else [(b"cookie", cookie.encode())]
    return Request({"type": "http", "headers": headers})


def test_claims_from_cookie_reads_the_session_cookie():
    public_id = uuid.uuid4()
    cookie = f"{settings.session_cookie_name}={create_session_token(public_id)}"

    claims = session_claims_from_cookie(_request(cookie))

    assert claims is not None
    assert claims.public_id == public_id


def test_claims_from_cookie_is_none_without_the_cookie():
    assert session_claims_from_cookie(_request(None)) is None
    assert session_claims_from_cookie(_request("other=value")) is None


# ── the user behind a session (shared by REST and WebSocket) ──────


async def test_load_active_user_finds_an_active_user(db_session, create_user):
    user = await create_user()

    assert await load_active_user(db_session, user.public_id) is user


async def test_load_active_user_ignores_a_deactivated_user(db_session, create_user):
    user = await create_user(is_active=False)

    assert await load_active_user(db_session, user.public_id) is None


async def test_load_active_user_ignores_a_deleted_user(db_session, create_user):
    user = await create_user(deleted_at=datetime.now(UTC))

    assert await load_active_user(db_session, user.public_id) is None


async def test_load_active_user_ignores_an_unknown_id(db_session):
    assert await load_active_user(db_session, uuid.uuid4()) is None
