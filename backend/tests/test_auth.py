import pytest
from sqlalchemy import func, select
from urllib.parse import parse_qs, urlparse

from app.core.oauth42 import FtProfile, OAuthLoginError
from app.models import OAuthAccount, User
from app.core.config import settings
from app.api import auth

LOGIN = "/api/auth/login"
CALLBACK = "/api/auth/callback"

def _query(response, key: str) -> str | None:
    values = parse_qs(urlparse(response.headers["location"]).query).get(key)
    return values[0] if values else None

async def _complete_login(client, code="auth-code"):
    """Walk the browser half of the flow: /auth/login hands back a state in a
    cookie, the intra hands it back on the callback."""
    login = await client.get(LOGIN)
    return await client.get(
        CALLBACK, params={"code": code, "state": _query(login, "state")}
    )


async def test_login_redirects_to_intra_and_sets_state_cookie(client, fake_ft):
    response = await client.get(LOGIN)

    assert response.status_code == 307
    assert response.headers["location"].startswith("https://intra.example/authorize")
    assert client.cookies.get("oauth_state")


async def test_callback_without_state_cookie_returns_303(client, fake_ft):
    response = await client.get(
        CALLBACK, params={"code": "auth-code", "state": "forged"}
    )

    assert response.status_code == 303
    assert _query(response, "auth_error") == "invalid_state"
    assert not client.cookies.get("session")


async def test_callback_with_mismatched_state_returns_303(client, fake_ft):
    await client.get(LOGIN)

    response = await client.get(
        CALLBACK, params={"code": "auth-code", "state": "forged"}
    )

    assert response.status_code == 303
    assert _query(response, "auth_error") == "invalid_state"
    assert not client.cookies.get("session")


async def test_callback_with_provider_error_opens_no_session(client, fake_ft):
    login = await client.get(LOGIN)
    state = login.headers["location"].split("state=")[1]

    response = await client.get(
        CALLBACK, params={"error": "access_denied", "state": state}
    )

    assert response.status_code == 303
    assert _query(response, "auth_error") == "denied"
    assert not client.cookies.get("session")
    assert fake_ft.exchanged_codes == []


async def test_callback_creates_user_and_oauth_account(client, fake_ft, db_session):
    response = await _complete_login(client)

    assert response.status_code == 303
    assert _query(response, "auth_error") is None
    assert client.cookies.get("session")
    assert fake_ft.exchanged_codes == ["auth-code"]

    user = await db_session.scalar(
        select(User).where(User.email == "jdoe@student.42.fr")
    )
    assert user is not None
    assert user.display_name == "jdoe"
    assert user.password_hash is None
    account = await db_session.scalar(
        select(OAuthAccount).where(OAuthAccount.user_id == user.id)
    )
    assert (account.provider, account.provider_account_id) == ("42", "42042")


async def test_callback_twice_does_not_duplicate_user(client, fake_ft, db_session):
    await _complete_login(client)
    await _complete_login(client)

    total = await db_session.scalar(
        select(func.count()).select_from(User).where(User.email == "jdoe@student.42.fr")
    )
    assert total == 1


async def test_callback_keeps_same_user_when_intra_login_changed(
    client, fake_ft, db_session
):
    await _complete_login(client)
    first = await db_session.scalar(select(User.public_id))

    # Same numeric id, renamed login and a new address: identity must hold.
    fake_ft.profile = FtProfile(
        id=42042, login="jdoe-renamed", email="jdoe-renamed@student.42.fr"
    )
    await _complete_login(client)

    users = (await db_session.scalars(select(User))).all()
    assert len(users) == 1
    assert users[0].public_id == first
    assert users[0].email == "jdoe-renamed@student.42.fr"
    # Seeded once at creation, never overwritten by a later intra rename.
    assert users[0].display_name == "jdoe"


async def test_callback_links_existing_oauth_only_user_matched_by_email(
    client, fake_ft, db_session, create_user
):
    existing = await create_user(
        email="jdoe@student.42.fr", display_name="Deja La", password_hash=None
    )

    await _complete_login(client)

    account = await db_session.scalar(
        select(OAuthAccount).where(OAuthAccount.provider_account_id == "42042")
    )
    assert account.user_id == existing.id
    assert existing.display_name == "Deja La"


async def test_callback_refuses_to_link_user_with_a_local_password(
    client, fake_ft, create_user
):
    await create_user(email="jdoe@student.42.fr", password_hash="hashed")

    response = await _complete_login(client)

    assert response.status_code == 303
    assert _query(response, "auth_error") == "email_taken"
    assert not client.cookies.get("session")


async def test_callback_fills_avatar_only_while_missing(client, fake_ft, db_session):
    await _complete_login(client)

    fake_ft.profile = FtProfile(
        id=42042, login="jdoe", email="jdoe@student.42.fr",
        avatar_url="https://cdn.intra.42.fr/users/jdoe.jpg",
    )
    await _complete_login(client)
    user = await db_session.scalar(select(User))
    assert user.avatar_path == "https://cdn.intra.42.fr/users/jdoe.jpg"

    # The user may have uploaded their own since: a new intra picture never wins.
    fake_ft.profile = FtProfile(
        id=42042, login="jdoe", email="jdoe@student.42.fr",
        avatar_url="https://cdn.intra.42.fr/users/jdoe-2.jpg",
    )
    await _complete_login(client)
    await db_session.refresh(user)
    assert user.avatar_path == "https://cdn.intra.42.fr/users/jdoe.jpg"


async def test_me_without_cookie_returns_401(client):
    response = await client.get("/api/v1/auth/me")

    assert response.status_code == 401


async def test_me_with_invalid_token_returns_401(client):
    client.cookies.set("session", "not-a-jwt")

    response = await client.get("/api/v1/auth/me")

    assert response.status_code == 401


async def test_me_for_inactive_user_returns_401(client, create_user, login_as):
    login_as(await create_user(is_active=False))

    response = await client.get("/api/v1/auth/me")

    assert response.status_code == 401


async def test_me_with_session_cookie_returns_current_user(
    client, create_user, login_as
):
    user = await create_user(display_name="Jean Dupont", bio="Bonjour")
    login_as(user)

    response = await client.get("/api/v1/auth/me")

    assert response.status_code == 200
    body = response.json()
    assert body["public_id"] == str(user.public_id)
    assert body["display_name"] == "Jean Dupont"
    assert body["role"] == "user"
    assert "password_hash" not in body


async def test_logout_clears_session_cookie(client, fake_ft):
    # Logs in for real so the cookie carries the domain and path the server
    # sets — that is what the expiry header has to match to evict it.
    await _complete_login(client)
    assert client.cookies.get("session")

    response = await client.post("/api/auth/logout")

    assert response.status_code == 204
    assert not client.cookies.get("session")
    assert (await client.get("/api/v1/auth/me")).status_code == 401


async def test_login_without_credentials_is_503(client, fake_ft, monkeypatch):
    monkeypatch.setattr(settings, "ft_client_id", "")
    assert (await client.get(LOGIN)).status_code == 503


async def test_callback_with_non_ascii_state_is_rejected_not_500(client, fake_ft):
    await client.get(LOGIN)
    response = await client.get(CALLBACK, params={"code": "auth-code", "state": "é"})
    assert response.status_code == 303
    assert _query(response, "auth_error") == "invalid_state"


async def test_callback_for_deactivated_user_opens_no_session(client, fake_ft, db_session):
    await _complete_login(client)
    user = await db_session.scalar(select(User))
    user.is_active = False
    await db_session.flush()
    client.cookies.clear()

    response = await _complete_login(client)
    assert _query(response, "auth_error") == "account_disabled"
    assert not client.cookies.get("session")


async def test_callback_reports_intra_failures(client, fake_ft):
    fake_ft.fail_with = OAuthLoginError("invalid_code", "stale")
    response = await _complete_login(client)
    assert response.status_code == 303
    assert _query(response, "auth_error") == "invalid_code"
    assert not client.cookies.get("session")


async def test_callback_lands_on_next(client, fake_ft):
    login = await client.get(LOGIN, params={"next": "/messages?tab=2"})
    response = await client.get(
        CALLBACK, params={"code": "auth-code", "state": _query(login, "state")}
    )

    assert response.status_code == 303
    assert response.headers["location"] == "/messages?tab=2"
    assert client.cookies.get("session")
    assert not client.cookies.get("oauth_next")


async def test_failed_callback_ignores_next(client, fake_ft):
    # the page asked for would only bounce back to the login
    fake_ft.fail_with = OAuthLoginError("invalid_code", "stale")
    login = await client.get(LOGIN, params={"next": "/messages"})
    response = await client.get(
        CALLBACK, params={"code": "auth-code", "state": _query(login, "state")}
    )

    assert _query(response, "auth_error") == "invalid_code"
    assert urlparse(response.headers["location"]).path == settings.post_login_redirect
    assert not client.cookies.get("oauth_next")


@pytest.mark.parametrize(
    "next_",
    ["//evil.com", "https://evil.com", "evil.com", "/\\evil.com", "/\t/evil.com",
     "/api/auth/login", "/" + "a" * auth.NEXT_MAX_LENGTH],
)
async def test_login_ignores_an_unsafe_next(client, fake_ft, next_):
    response = await client.get(LOGIN, params={"next": next_})

    assert response.status_code == 307
    assert not client.cookies.get("oauth_next")


async def test_callback_ignores_a_forged_next_cookie(client, fake_ft):
    login = await client.get(LOGIN)
    client.cookies.set("oauth_next", "%2F%2Fevil.com", path="/api/auth/")

    response = await client.get(
        CALLBACK, params={"code": "auth-code", "state": _query(login, "state")}
    )

    assert "oauth_next=%2F%2Fevil.com" in response.request.headers["cookie"]
    assert response.headers["location"] == settings.post_login_redirect
    assert client.cookies.get("session")


async def test_login_without_next_drops_a_stale_one(client, fake_ft):
    await client.get(LOGIN, params={"next": "/messages"})
    assert client.cookies.get("oauth_next")

    await client.get(LOGIN)

    assert not client.cookies.get("oauth_next")


async def test_callback_survives_losing_the_first_login_race(
    client, fake_ft, db_session, create_user, monkeypatch
):
    # The account already exists by the time this callback inserts it (another
    # callback won). Committed so the app's rollback-to-savepoint keeps it.
    winner = await create_user(email="jdoe@student.42.fr", password_hash=None)
    db_session.add(OAuthAccount(provider="42", provider_account_id="42042", user=winner))
    await db_session.commit()

    real_find, calls = auth._find_account, 0

    async def miss_once(session, pid):
        nonlocal calls
        calls += 1
        return None if calls == 1 else await real_find(session, pid)

    monkeypatch.setattr(auth, "_find_account", miss_once)

    response = await _complete_login(client)

    assert response.status_code == 303 and _query(response, "auth_error") is None
    assert client.cookies.get("session")
    assert calls == 2  # the IntegrityError path re-fetched the winner's account
