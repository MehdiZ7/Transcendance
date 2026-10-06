import logging
from collections.abc import Awaitable
from typing import Any
from urllib.parse import urlencode

import httpx
from fastapi import Request
from pydantic import BaseModel, ValidationError

from app.core.config import settings

logger = logging.getLogger(__name__)


class OAuthLoginError(Exception):
    """A 42 login that cannot complete.
    code is short and machine-readable:
    the callback hands it back to the browser as ?auth_error=<code>, so it
    must never carry anything sensitive.
    The message is for the logs."""

    def __init__(self, code: str, detail: str) -> None:
        super().__init__(detail)
        self.code = code

class FtProfile(BaseModel):
    id: int
    login: str
    email: str
    avatar_url: str | None = None


class FtOAuthClient:
    """Talks to the 42 intra OAuth endpoints. Both the token exchange and the
    profile fetch are server-to-server: the client secret and the intra access
    token never reach the browser, and the token is not persisted."""

    def __init__(self, http: httpx.AsyncClient) -> None:
        self._http = http

    def authorize_url(self, state: str) -> str:
        query = urlencode(
            {
                "client_id": settings.ft_client_id,
                "redirect_uri": settings.ft_redirect_uri,
                "response_type": "code",
                "scope": settings.ft_scope,
                "state": state,
            }
        )
        return f"{settings.ft_authorize_url}?{query}"

    async def exchange_code(self, code: str) -> str:
        payload = await self._call(
            "token exchange",
            self._http.post(
                settings.ft_token_url,
                data={
                    "grant_type": "authorization_code",
                    "client_id": settings.ft_client_id,
                    "client_secret": settings.ft_client_secret,
                    "code": code,
                    "redirect_uri": settings.ft_redirect_uri,
                },
            ),
            # 400/401 here means the code is bad, expired or already used
            # (the user replayed the callback URL)
            client_error="invalid_code",
        )
        access_token = payload.get("access_token") if isinstance(payload, dict) else None
        if not access_token:
            raise OAuthLoginError("intra_unavailable", "42 API returned no access token")
        return access_token

    async def fetch_profile(self, access_token: str) -> FtProfile:
        payload = await self._call(
            "profile fetch",
            self._http.get(
                settings.ft_me_url,
                headers={"Authorization": f"Bearer {access_token}"},
            ),
        )
        try:
            return FtProfile(
                id=payload["id"],
                login=payload["login"],
                email=payload["email"],
                avatar_url=(payload.get("image") or {}).get("link"),
            )
        except (KeyError, TypeError, AttributeError, ValidationError) as exc:
            raise OAuthLoginError(
                "invalid_profile", "42 API returned an unexpected profile"
            ) from exc

    async def _call(
        self,
        step: str,
        request: Awaitable[httpx.Response],
        *,
        client_error: str = "intra_unavailable",
    ) -> Any:
        """Anything the intra does wrong is an OAuthLoginError, never a 500.
        Logged with the status only: a body could echo the code or the token."""
        try:
            response = await request
        except httpx.HTTPError as exc:
            logger.warning("42 API %s failed: %s", step, type(exc).__name__)
            raise OAuthLoginError("intra_unavailable", f"42 API {step} failed") from exc
        if response.is_error:
            logger.warning("42 API %s returned %s", step, response.status_code)
            code = client_error if response.is_client_error else "intra_unavailable"
            raise OAuthLoginError(code, f"42 API {step} returned {response.status_code}")
        try:
            return response.json()
        except ValueError as exc:
            logger.warning("42 API %s returned invalid JSON", step)
            raise OAuthLoginError(
                "intra_unavailable", f"42 API {step} returned invalid JSON"
            ) from exc


def get_ft_client(request: Request) -> FtOAuthClient:
    """Injection seam: tests override this dependency with a fake so the OAuth
    flow can be exercised without touching the network."""
    return FtOAuthClient(request.app.state.http)
