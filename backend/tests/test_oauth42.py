import httpx
import pytest

from app.core.oauth42 import FtOAuthClient, OAuthLoginError


def _client(handler) -> FtOAuthClient:
    return FtOAuthClient(httpx.AsyncClient(transport=httpx.MockTransport(handler)))


async def test_exchange_code_posts_the_code_and_returns_the_token():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/oauth/token"
        assert b"grant_type=authorization_code" in request.content
        assert b"code=auth-code" in request.content
        return httpx.Response(200, json={"access_token": "tok"})

    assert await _client(handler).exchange_code("auth-code") == "tok"


async def test_rejected_code_is_the_users_fault():
    handler = lambda request: httpx.Response(401, json={"error": "invalid_grant"})  # noqa: E731
    with pytest.raises(OAuthLoginError) as exc:
        await _client(handler).exchange_code("stale")
    assert exc.value.code == "invalid_code"


async def test_intra_outage_is_reported_as_unavailable():
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("down")

    with pytest.raises(OAuthLoginError) as exc:
        await _client(handler).exchange_code("auth-code")
    assert exc.value.code == "intra_unavailable"


async def test_fetch_profile_maps_the_intra_shape():
    handler = lambda request: httpx.Response(  # noqa: E731
        200,
        json={"id": 1, "login": "jdoe", "email": "j@d.fr", "image": {"link": "https://cdn/x.jpg"}},
    )
    profile = await _client(handler).fetch_profile("tok")
    assert (profile.id, profile.login, profile.avatar_url) == (1, "jdoe", "https://cdn/x.jpg")


async def test_profile_without_id_is_invalid_profile():
    handler = lambda request: httpx.Response(200, json={"login": "jdoe"})  # noqa: E731
    with pytest.raises(OAuthLoginError) as exc:
        await _client(handler).fetch_profile("tok")
    assert exc.value.code == "invalid_profile"
