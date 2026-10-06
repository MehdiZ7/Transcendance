"""FastAPI application entrypoint."""

import asyncio
import contextlib
import logging
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

import httpx
from fastapi import Depends, FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from prometheus_fastapi_instrumentator import Instrumentator
from sqlalchemy.exc import DBAPIError

from app.api import auth, ws
from app.api.v1 import router
from app.core.config import settings
from app.core.db import async_session, engine
from app.core.ratelimit import limit_requests
from app.core.uploads import purge_orphaned_uploads
from app.realtime import hub

logger = logging.getLogger(__name__)


async def _purge_uploads_periodically() -> None:
    """Runs for the life of the app: an upload nothing ever attached is
    otherwise never freed. Errors are logged and swallowed - one missed run
    is not worth crashing the process over, there is always a next one."""
    while True:
        await asyncio.sleep(settings.upload_purge_interval_seconds)
        try:
            async with async_session() as session:
                removed = await purge_orphaned_uploads(
                    session, settings.upload_purge_after_seconds
                )
            if removed:
                logger.info("purged %d orphaned upload(s)", removed)
        except Exception:
            logger.exception("orphaned upload purge failed")


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None]:
    """Startup and shutdown around the app: one shared HTTP client for the
    intra, the realtime hub, and the orphaned-upload purge loop on the way
    up, the database pool disposed on the way down."""
    # safe_database_url masks the password, never log database_url directly
    logger.info("api starting, db=%s", settings.safe_database_url)
    async with httpx.AsyncClient(timeout=10.0) as http:
        app.state.http = http
        await hub.start()
        purge_task = asyncio.create_task(_purge_uploads_periodically())
        try:
            yield
        finally:
            purge_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await purge_task
            await hub.stop()
    await engine.dispose()


app = FastAPI(
    title="lb42 API",
    version="0.1",
    docs_url="/api/v1/docs",
    openapi_url="/api/openapi.json",
    lifespan=lifespan,
)

# PostgreSQL cannot store a NUL character: 22021 (character_not_in_repertoire)
# in text, 22P05 (untranslatable_character) in JSONB. The fields people type
# refuse it up front (NoNul in schemas/limits.py); this turns any other one
# into a 422 instead of a 500. Every other database error is raised again.
_UNSTORABLE_TEXT = {"22021", "22P05"}


@app.exception_handler(DBAPIError)
async def _unstorable_text(request: Request, exc: DBAPIError) -> JSONResponse:
    if getattr(exc.orig, "sqlstate", None) in _UNSTORABLE_TEXT:
        return JSONResponse(
            status_code=422, content={"detail": "Text contains a character that cannot be stored"}
        )
    raise exc


Instrumentator(
    should_group_status_codes=False,
    should_ignore_untemplated=True,
    excluded_handlers=[
        "/metrics",
        "/api/v1/health",
        "/api/v1/analytics/stream",
    ]
).instrument(app).expose(app, endpoint="/metrics", include_in_schema=False)

if settings.cors_origins_list:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins_list,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

app.include_router(auth.router, prefix="/api", tags=["auth"])
app.include_router(ws.router, prefix="/api", tags=["realtime"])
app.include_router(router, prefix="/api/v1", dependencies=[Depends(limit_requests)])
