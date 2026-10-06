"""Configuration with types, read from env

pydantic-settings fails on start if variable missing

secrets :

DATABASE_URL not stored : composed from  POSTGRES_*

X_FILE=/path, content read as value format for secrets Docker/Podman
(/run/secrets/…), secret never appears in docker inspect, /proc/<pid>/environ, or child processes
"""

import logging
import os
import secrets
from functools import lru_cache
from pathlib import Path
from typing import Literal, Self
from urllib.parse import quote_plus

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

logger = logging.getLogger(__name__)


class Settings(BaseSettings):
    """Every setting the app reads from the environment

    Built once at import so a missing or malformed value fails at startup
    rather than halfway through serving a request
    """

    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )

    environment: Literal["dev", "prod"] = "dev"
    sql_echo: bool = False

    # Host and port the browser uses to reach nginx; only needed to derive
    # ft_redirect_uri below.
    server_name: str = "localhost"
    https_port: int = 443

    # Postgres, composed by database_url below.
    postgres_user: str = "lb42"
    postgres_password: str = ""
    postgres_db: str = "lb42db"
    postgres_host: str = "db"
    postgres_port: int = 5432

    # Provided via the SECRET_KEY docker secret in prod (entrypoint.sh turns
    # SECRET_KEY_FILE into SECRET_KEY before uvicorn starts). The random
    # fallback keeps dev/tests working without that setup, at the cost of
    # invalidating sessions across restarts.
    secret_key: str = ""

    # 42 intra OAuth application credentials
    # (https://profile.intra.42.fr/oauth/applications), provided the same way
    # via FT_CLIENT_ID / FT_CLIENT_SECRET. Empty by default: /auth/login
    # answers 503 until they're filled in (see Makefile).
    ft_client_id: str = ""
    ft_client_secret: str = ""
    # Must match the intra byte for byte. Empty = derived from server_name
    # and https_port; set it only when the browser reaches the API some other
    # way (bare uvicorn: http://localhost:8000/api/auth/callback).
    ft_redirect_uri: str = "https://localhost:8443/api/auth/callback"
    ft_authorize_url: str = "https://api.intra.42.fr/oauth/authorize"
    ft_token_url: str = "https://api.intra.42.fr/oauth/token"
    ft_me_url: str = "https://api.intra.42.fr/v2/me"
    ft_scope: str = "public"

    session_cookie_name: str = "session"
    session_max_age: int = 60 * 60 * 24 * 7
    oauth_state_cookie_name: str = "oauth_state"
    oauth_next_cookie_name: str = "oauth_next"
    oauth_state_max_age: int = 600
    cookie_secure: bool = True

    # Where the browser lands after the callback. Relative to the proxy root.
    post_login_redirect: str = "/"

    # Email + password accounts (POST /api/auth/register, /login, /password).
    # Comma-separated domains refused at registration: their owners sign in
    # with 42, and an unverified local account squatting their address would
    # lock them out (the 42 callback never links an account with a password).
    register_blocked_email_domains: str = "student.42.fr"
    # A 42 account sets its first password only from a session opened this
    # many seconds ago at most: with no old password to prove, a fresh 42
    # login is the proof.
    password_reauth_max_age: int = 10 * 60

    # Comma-separated. Empty = middleware off: nginx serves the front and the
    # API on one origin.
    cors_origins: str = ""

    # Per-user quotas, enforced by app/core/quotas.py: how many rows one user
    # can create. 0 refuses every creation; use a large number to relax one.
    quota_active_listings: int = 50  # active or draft, not deleted
    quota_listings_per_day: int = 20  # created in 24 h, deleted ones included
    quota_conversations_per_day: int = 30  # opened as buyer in 24 h
    quota_messages_per_conversation: int = 5000  # listing chat and friend DM
    quota_reports_per_day: int = 10
    quota_pending_friend_requests: int = 50  # sent and not answered
    quota_friends: int = 500
    quota_favorites: int = 500
    quota_blocks: int = 500

    # Image uploads (POST /uploads/images), see app/core/uploads.py. Files go
    # under media_root/images/<user public_id>/ and nginx serves them at /media/.
    media_root: str = "/srv/media"
    max_upload_bytes: int = 5 * 1024 * 1024
    quota_uploads_per_day: int = 50
    quota_upload_bytes: int = 100 * 1024 * 1024  # stored per user, all files together
    # Comma-separated hosts an https image URL may point at (the same ones the
    # nginx CSP allows for img-src): the 42 avatars.
    allowed_image_hosts: str = "cdn.intra.42.fr"
    # An upload attached to nothing (listing_images.storage_path or
    # users.avatar_path) after this long is considered abandoned and purged.
    upload_purge_after_seconds: int = 24 * 60 * 60
    upload_purge_interval_seconds: int = 60 * 60  # how often the purge runs

    # REST rate limits per logged-in user, see app/core/ratelimit.py. 0 = off.
    rate_reads_per_minute: int = 300  # every GET, all routes together
    rate_writes_per_minute: int = 60  # every POST/PATCH/DELETE, all routes together
    rate_messages_per_minute: int = 30  # listing chat and friend DM, together
    rate_listings_per_hour: int = 10
    rate_reports_per_hour: int = 10
    rate_friend_requests_per_hour: int = 20
    rate_uploads_per_hour: int = 30
    # Password checks (login, change) per email, whoever asks: no session here
    rate_password_attempts_per_hour: int = 10

    # Websocket config
    # Comma-separated origins allowed to open the socket. Empty = derived
    # from server_name and https_port, the origin nginx serves the front on.
    ws_allowed_origins: str = ""
    ws_send_queue_max: int = 100  # queue max length by session
    ws_replay_max: int = 100  # replay max length , (0 = no replay)
    ws_session_ttl: int = 60  # session time to live
    ws_max_sessions_per_user: int = 8
    ws_max_topics_per_session: int = 50
    ws_max_frame_bytes: int = 4096
    ws_rate_limit_per_10s: int = 1000  # client frames per user (0 = no limit)
    ws_heartbeat_interval: int = 25
    ws_handshake_timeout: int = 10

    @model_validator(mode="after")
    def _fill_derived(self) -> Self:
        if not self.ft_redirect_uri:
            port = "" if self.https_port == 443 else f":{self.https_port}"
            self.ft_redirect_uri = f"https://{self.server_name}{port}/api/auth/callback"
        if not self.secret_key:
            if self.environment == "prod":
                raise ValueError("SECRET_KEY must be set when ENVIRONMENT=prod")
            # Dev/tests only: sessions die with the process, and with several
            # uvicorn workers each one would sign with its own key.
            logger.warning("SECRET_KEY not set: using a random key for this process")
            self.secret_key = secrets.token_urlsafe(32)
        return self

    @property
    def ws_allowed_origins_set(self) -> frozenset[str]:
        configured = {
            origin.strip().rstrip("/").lower()
            for origin in self.ws_allowed_origins.split(",")
            if origin.strip()
        }
        if configured:
            return frozenset(configured)
        port = "" if self.https_port == 443 else f":{self.https_port}"
        return frozenset({f"https://{self.server_name}{port}".lower()})

    @property
    def register_blocked_email_domains_set(self) -> frozenset[str]:
        return frozenset(
            domain.strip().lower()
            for domain in self.register_blocked_email_domains.split(",")
            if domain.strip()
        )

    @property
    def cors_origins_list(self) -> list[str]:
        return [
            origin.strip() for origin in self.cors_origins.split(",") if origin.strip()
        ]

    @property
    def database_url(self) -> str:
        """Builds the database URL from the POSTGRES_* settings

        The 'postgresql+asyncpg://' prefix is mandatory: plain 'postgresql://'
        selects psycopg2 instead and fails with a synchronous-driver error.

        'quote_plus' is applied to the user and the password because a @,
        a / or a # in the password would silently corrupt the URL
        """
        if not self.postgres_password:
            raise RuntimeError(
                "POSTGRES_PASSWORD is not set. Set it in secrets/ (POSTGRES_PASSWORD_FILE)."
            )
        user = quote_plus(self.postgres_user)
        password = quote_plus(self.postgres_password)
        return (
            f"postgresql+asyncpg://{user}:{password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )

    @property
    def safe_database_url(self) -> str:
        """DB URL with the password hidden

        The only form that may ever reach a log
        """
        url = self.database_url
        if "@" not in url:
            return url
        scheme, _, rest = url.partition("://")
        credentials, _, host = rest.partition("@")
        user = credentials.partition(":")[0]
        return f"{scheme}://{user}:***@{host}"


FILE_SUFFIX = "_FILE"


def expand_file_secrets(environ: dict[str, str] | None = None) -> list[str]:
    """Replace ..._FILE=/path by ..=<content>

    Variable already defined not replaced : priority on explicit env
    """
    env = environ if environ is not None else os.environ
    resolved: list[str] = []

    for key in [k for k in env if k.endswith(FILE_SUFFIX)]:
        target = key[: -len(FILE_SUFFIX)]
        if not target or env.get(target):
            continue
        path = Path(env[key])
        try:
            env[target] = path.read_text(encoding="utf-8").strip()
        except OSError as exc:
            raise RuntimeError(
                f"{key} pointing to {path} cannot be read: {exc}"
            ) from exc
        resolved.append(target)

    return resolved


@lru_cache
def get_settings() -> Settings:
    """env read once then used everywhere"""
    expand_file_secrets()
    return Settings()


settings = get_settings()
