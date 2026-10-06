from datetime import UTC, datetime, timedelta

import jwt
import pytest
from sqlalchemy import select

from app.core.config import settings
from app.core.passwords import hash_password, verify_password
from app.core.security import ALGORITHM
from app.models import User

REGISTER = "/api/auth/register"
PASSWORD_LOGIN = "/api/auth/login"
CHANGE = "/api/auth/password"
LOGOUT = "/api/auth/logout"
ME = "/api/v1/auth/me"


def _login_long_ago(client, user: User) -> None:
    """A valid session, opened an hour ago: too old to set a first password."""
    issued_at = datetime.now(UTC) - timedelta(hours=1)
    token = jwt.encode(
        {"sub": str(user.public_id), "iat": issued_at, "exp": issued_at + timedelta(days=1)},
        settings.secret_key,
        algorithm=ALGORITHM,
    )
    client.cookies.set(settings.session_cookie_name, token)


async def test_register_creates_a_user_and_opens_a_session(client, db_session):
    response = await client.post(
        REGISTER,
        json={"email": "new@42.fr", "password": "Secret123", "display_name": "New"},
    )

    assert response.status_code == 201
    body = response.json()
    assert body["email"] == "new@42.fr"
    assert body["display_name"] == "New"
    assert body["has_password"] is True
    assert "password_hash" not in body
    assert client.cookies.get("session")

    me = await client.get(ME)
    assert me.status_code == 200
    assert me.json()["email"] == "new@42.fr"

    user = await db_session.scalar(select(User).where(User.email == "new@42.fr"))
    assert user.password_hash.startswith("$argon2id$")
    assert await verify_password("Secret123", user.password_hash)
    # nothing has proven the address yet
    assert user.email_verified_at is None


@pytest.mark.parametrize("password_hash", ["existing", None], ids=["local", "42-only"])
async def test_register_rejects_a_duplicate_email_whatever_its_case(
    client, create_user, password_hash
):
    await create_user(email="dup@42.fr", password_hash=password_hash)

    response = await client.post(
        REGISTER,
        json={"email": "DUP@42.fr", "password": "Secret123", "display_name": "Dup"},
    )

    assert response.status_code == 409
    assert not client.cookies.get("session")


async def test_register_refuses_a_42_student_address(client, db_session):
    response = await client.post(
        REGISTER,
        json={"email": "jdoe@student.42.fr", "password": "Secret123", "display_name": "J"},
    )

    assert response.status_code == 403
    assert not await db_session.scalar(select(User).where(User.email == "jdoe@student.42.fr"))


@pytest.mark.parametrize(
    "payload",
    [
        {"email": "not-an-email", "password": "Secret123", "display_name": "X"},
        {"email": "ok@42.fr", "password": "short", "display_name": "X"},
        {"email": "ok@42.fr", "password": "x" * 129, "display_name": "X"},
        {"email": "ok@42.fr", "password": "Secret123", "display_name": "   "},
    ],
    ids=["bad email", "short password", "long password", "blank name"],
)
async def test_register_validates_its_input(client, payload):
    assert (await client.post(REGISTER, json=payload)).status_code == 422


async def test_login_with_correct_credentials_ignores_email_case(client, create_user):
    user = await create_user(email="me@42.fr", password_hash=await hash_password("Secret123"))

    response = await client.post(
        PASSWORD_LOGIN, json={"email": "ME@42.fr", "password": "Secret123"}
    )

    assert response.status_code == 200
    assert response.json()["public_id"] == str(user.public_id)
    assert client.cookies.get("session")


async def test_login_refusals_all_look_the_same(client, create_user):
    await create_user(email="me@42.fr", password_hash=await hash_password("Secret123"))
    await create_user(email="oauth@42.fr", password_hash=None)

    wrong = await client.post(PASSWORD_LOGIN, json={"email": "me@42.fr", "password": "nope"})
    unknown = await client.post(
        PASSWORD_LOGIN, json={"email": "ghost@42.fr", "password": "Secret123"}
    )
    oauth_only = await client.post(
        PASSWORD_LOGIN, json={"email": "oauth@42.fr", "password": "Secret123"}
    )

    for response in (wrong, unknown, oauth_only):
        assert response.status_code == 401
        assert response.json() == {"detail": "Invalid email or password"}
    assert not client.cookies.get("session")


@pytest.mark.parametrize(
    "disabled",
    [{"is_active": False}, {"deleted_at": datetime.now(UTC)}],
    ids=["suspended", "deleted"],
)
async def test_login_rejects_a_disabled_account(client, create_user, disabled):
    await create_user(
        email="off@42.fr", password_hash=await hash_password("Secret123"), **disabled
    )

    response = await client.post(
        PASSWORD_LOGIN, json={"email": "off@42.fr", "password": "Secret123"}
    )

    assert response.status_code == 403
    assert not client.cookies.get("session")


async def test_password_checks_are_limited_per_email(client, monkeypatch):
    monkeypatch.setattr(settings, "rate_password_attempts_per_hour", 2)
    attempt = {"email": "target@42.fr", "password": "guess-1234"}

    statuses = [(await client.post(PASSWORD_LOGIN, json=attempt)).status_code for _ in range(3)]
    other = await client.post(PASSWORD_LOGIN, json={**attempt, "email": "other@42.fr"})

    assert statuses == [401, 401, 429]
    assert other.status_code == 401  # another account is not affected


async def test_change_password_requires_authentication(client):
    response = await client.post(
        CHANGE, json={"new_password": "NewSecret1", "current_password": "x"}
    )

    assert response.status_code == 401


async def test_change_password_checks_and_replaces(client, create_user, login_as):
    user = await create_user(
        email="ch@42.fr", password_hash=await hash_password("OldSecret1")
    )
    login_as(user)

    wrong = await client.post(
        CHANGE, json={"new_password": "NewSecret1", "current_password": "bad"}
    )
    assert wrong.status_code == 400
    missing = await client.post(CHANGE, json={"new_password": "NewSecret1"})
    assert missing.status_code == 400

    ok = await client.post(
        CHANGE, json={"new_password": "NewSecret1", "current_password": "OldSecret1"}
    )
    assert ok.status_code == 204

    await client.post(LOGOUT)
    old = await client.post(PASSWORD_LOGIN, json={"email": "ch@42.fr", "password": "OldSecret1"})
    assert old.status_code == 401
    login = await client.post(
        PASSWORD_LOGIN, json={"email": "ch@42.fr", "password": "NewSecret1"}
    )
    assert login.status_code == 200


async def test_change_password_guesses_are_limited(client, create_user, login_as, monkeypatch):
    monkeypatch.setattr(settings, "rate_password_attempts_per_hour", 1)
    user = await create_user(
        email="guess@42.fr", password_hash=await hash_password("OldSecret1")
    )
    login_as(user)

    body = {"new_password": "NewSecret1", "current_password": "guess"}
    first = await client.post(CHANGE, json=body)
    second = await client.post(CHANGE, json=body)

    assert (first.status_code, second.status_code) == (400, 429)


async def test_42_account_sets_a_first_password_right_after_a_42_login(
    client, db_session, create_user, login_as
):
    user = await create_user(email="oauth@42.fr", password_hash=None)
    login_as(user)  # a session opened just now

    response = await client.post(CHANGE, json={"new_password": "FirstSecret1"})
    assert response.status_code == 204

    await db_session.refresh(user)
    assert user.password_hash is not None

    login = await client.post(
        PASSWORD_LOGIN, json={"email": "oauth@42.fr", "password": "FirstSecret1"}
    )
    assert login.status_code == 200


async def test_42_account_cannot_set_a_password_from_an_old_session(
    client, db_session, create_user
):
    user = await create_user(email="oauth@42.fr", password_hash=None)
    _login_long_ago(client, user)

    response = await client.post(CHANGE, json={"new_password": "FirstSecret1"})

    assert response.status_code == 403
    await db_session.refresh(user)
    assert user.password_hash is None


async def test_has_password_flag_reflects_the_account(client, create_user, login_as):
    password_user = await create_user(
        email="wpw@42.fr", password_hash=await hash_password("Secret123")
    )
    login_as(password_user)
    assert (await client.get(ME)).json()["has_password"] is True
    assert (await client.get("/api/v1/users/me")).json()["has_password"] is True

    oauth_user = await create_user(email="npw@42.fr", password_hash=None)
    login_as(oauth_user)
    assert (await client.get(ME)).json()["has_password"] is False
    assert (await client.get("/api/v1/users/me")).json()["has_password"] is False
