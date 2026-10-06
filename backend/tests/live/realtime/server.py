"""Live test bench for app.core.realtime.

DEV ONLY: the principal comes from the query string, there is no auth and no
Origin check. Never expose it.

    uv run python tests/live/realtime/server.py
    # then open http://127.0.0.1:8765

The whole real stack runs here (protocol, router, broker, sessions, registry,
asyncio transport). Only the wiring is local: a demo router, a Starlette
adapter for the `Socket` port and a few HTTP routes to publish as business
code would and to look inside the registry.

Environment: PORT (8765), LIVE_QUEUE (20), LIVE_REPLAY (50), LIVE_TTL (30).
"""

import asyncio
import logging
import os
import time
from collections import deque
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

import uvicorn
from fastapi import FastAPI, Query, WebSocket
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from app.api.ws import StarletteSocket
from app.core.config import settings
from app.core.realtime.broker import Broker
from app.core.realtime.limiter import WindowLimiter
from app.core.realtime.protocol import ClientMessage, EventFrame
from app.core.realtime.publisher import local_publisher
from app.core.realtime.registry import Registry
from app.core.realtime.router import Router
from app.core.realtime.session import Session
from app.core.realtime.topics import Topic
from app.core.realtime.transport import CloseCode, Connection

logger = logging.getLogger("realtime.live")

STATIC = Path(__file__).parent / "static"
PORT = int(os.environ.get("PORT", "8765"))
# Small on purpose: a burst of a few dozen events is enough to see a gap
QUEUE_LIMIT = int(os.environ.get("LIVE_QUEUE", "20"))
REPLAY_LIMIT = int(os.environ.get("LIVE_REPLAY", "50"))
TTL = float(os.environ.get("LIVE_TTL", "30"))
IDLE_TIMEOUT = 60.0
RATE_LIMIT = settings.ws_rate_limit_per_10s
RATE_WINDOW = 10.0
HISTORY = 10

PRESENCE = Topic("presence")


# ── demo business code ────────────────────────────────────────────

router = Router()
broker = Broker()
publisher = local_publisher(broker)
history: dict[str, deque[dict[str, Any]]] = {}


@router.topic("conversation")
def may_read_conversation(principal: str, topic: Topic) -> bool:
    """Any conversation id, except `secret`, which only `admin` may read."""
    return topic.id is not None and (topic.id != "secret" or principal == "admin")


@router.on_subscribe("conversation")
def conversation_history(session: Session, topic: Topic) -> list[EventFrame]:
    assert topic.id is not None
    messages = list(history.get(topic.id, ()))
    return [
        EventFrame(
            type="message.history",
            topic_kind=topic.kind,
            topic_id=topic.id,
            payload={"messages": messages},
        )
    ]


@router.topic("presence")
def presence_is_public(principal: str, topic: Topic) -> bool:
    return topic.id is None


@router.message("message.create")
def create_message(session: Session, frame: ClientMessage) -> None:
    text = frame.payload.get("text")
    if not isinstance(text, str) or not 0 < len(text) <= 500:
        raise ValueError("payload.text must be a string of 1 to 500 chars")
    assert frame.topic_id is not None  # the authorizer requires one
    message = {"text": text, "by": session.principal, "at": time.time()}
    history.setdefault(frame.topic_id, deque(maxlen=HISTORY)).append(message)
    publisher.publish("message.created", Topic.of(frame), message)


@router.message("typing.start")
def typing(session: Session, frame: ClientMessage) -> None:
    publisher.publish("typing.started", Topic.of(frame), {"by": session.principal})


registry = Registry(
    router,
    broker,
    ttl=TTL,
    queue_limit=QUEUE_LIMIT,
    replay_limit=REPLAY_LIMIT,
    limiter=WindowLimiter(RATE_LIMIT, RATE_WINDOW) if RATE_LIMIT > 0 else None,
)


# ── app ───────────────────────────────────────────────────────────


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    router.check()
    router.freeze()

    async def sweep() -> None:
        while True:
            await asyncio.sleep(5)
            if swept := registry.sweep():
                logger.info("swept %d session(s)", swept)

    sweeper = asyncio.create_task(sweep())
    logger.info(
        "bench on http://127.0.0.1:%d  queue=%d replay=%d ttl=%.0fs",
        PORT,
        QUEUE_LIMIT,
        REPLAY_LIMIT,
        TTL,
    )
    yield
    sweeper.cancel()
    registry.close_all()


app = FastAPI(title="realtime bench", lifespan=lifespan)
app.mount("/static", StaticFiles(directory=STATIC), name="static")


@app.get("/", include_in_schema=False)
async def index() -> FileResponse:
    return FileResponse(STATIC / "index.html")


@app.websocket("/ws")
async def ws(
    websocket: WebSocket,
    user: str = Query(min_length=1, max_length=32, pattern=r"^[\w.-]+$"),
) -> None:
    await websocket.accept()
    connection = Connection(
        StarletteSocket(websocket, max_bytes=settings.ws_max_frame_bytes),
        registry,
        user,
        idle_timeout=IDLE_TIMEOUT,
    )
    publisher.publish("presence.online", PRESENCE, {"user": user})
    code = await connection.run()
    logger.info("%s disconnected with %d", user, code)
    if code != CloseCode.REPLACED:
        publisher.publish("presence.offline", PRESENCE, {"user": user})


class PublishIn(BaseModel):
    type: str = Field(min_length=1)
    topic_kind: str = Field(min_length=1)
    topic_id: str | None = None
    payload: dict[str, Any] = Field(default_factory=dict)


class BurstIn(BaseModel):
    topic_kind: str = Field(min_length=1)
    topic_id: str | None = None
    count: int = Field(ge=1, le=1000)


@app.post("/api/publish")
async def publish(body: PublishIn) -> dict[str, int]:
    topic = Topic(body.topic_kind, body.topic_id or None)
    return {"delivered": publisher.publish(body.type, topic, body.payload)}


@app.post("/api/burst")
async def burst(body: BurstIn) -> dict[str, int]:
    """Publish `count` events without yielding: nobody can flush in between."""
    topic = Topic(body.topic_kind, body.topic_id or None)
    delivered = sum(
        publisher.publish("burst.tick", topic, {"i": i, "of": body.count})
        for i in range(1, body.count + 1)
    )
    return {"delivered": delivered}


@app.get("/api/stats")
async def stats() -> dict[str, Any]:
    return {
        "config": {
            "queue_limit": QUEUE_LIMIT,
            "replay_limit": REPLAY_LIMIT,
            "ttl": TTL,
            "idle_timeout": IDLE_TIMEOUT,
            "rate_limit": f"{RATE_LIMIT}/{RATE_WINDOW:.0f}s" if RATE_LIMIT > 0 else "off",
            "heartbeat": settings.ws_heartbeat_interval,
        },
        "sessions": [
            {
                "token": s.id,
                "principal": s.principal,
                "state": s.state,
                "epoch": s.epoch,
                "seq": s.last_seq,
                "pending": s.pending,
                "gapped": s.gapped,
                "idle": round(s.idle_for(), 1),
                "topics": sorted(str(t) for t in s.topics()),
            }
            for s in registry.sessions()
        ],
        "topics": {
            str(t): len(broker.subscribers(t))
            for t in sorted(broker.active_topics(), key=str)
        },
    }


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO, format="%(levelname)s %(name)s: %(message)s"
    )
    uvicorn.run(
        app, host="127.0.0.1", port=PORT, ws_max_size=settings.ws_max_frame_bytes
    )
