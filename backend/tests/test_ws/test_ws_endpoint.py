"""Endpoint tests for /api/ws, through the real application.

httpx's ASGITransport (the `client` fixture) does not speak WebSocket, so
these use Starlette's TestClient. It runs the app in its own event loop, so
no database session can cross over: the user lookup is swapped for an
in-memory one (`get_user_loader`) and the hub for one with a test router
(`get_hub`). The Origin check, the cookie and the JWT go through the real
code. The TestClient is not entered as a context manager, so the app
lifespan (and the shared engine) stays out of it.
"""

import json
import uuid
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import jwt
import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from app.api.ws import get_user_loader
from app.core.config import settings
from app.core.realtime.hub import Hub
from app.core.realtime.protocol import ClientMessage
from app.core.realtime.router import Router
from app.core.realtime.session import Session
from app.core.realtime.topics import Topic
from app.core.realtime.transport import CloseCode
from app.core.security import ALGORITHM, create_session_token
from app.main import app
from app.realtime import get_hub
from app import realtime_topics
from app.realtime_topics import PRESENCE

ORIGIN = "https://app.test"
ALICE = uuid.uuid4()
BOB = uuid.uuid4()
GONE = uuid.uuid4()  # a valid token whose user is deactivated or deleted


def inbox(user: uuid.UUID) -> dict:
    return {"type": "subscribe", "topic_kind": "inbox", "topic_id": str(user)}


# ── fixtures ──────────────────────────────────────────────────────


@pytest.fixture
def hub() -> Hub:
    router = Router()

    @router.topic("inbox")
    def own_inbox_only(principal: str, topic: Topic) -> bool:
        return topic.id == principal

    @router.topic("room")
    def public_rooms(principal: str, topic: Topic) -> bool:
        return topic.id is not None

    @router.message("note.send")
    def send_note(session: Session, frame: ClientMessage) -> None:
        hub.publisher.publish(
            "note.created",
            Topic.of(frame),
            {"text": frame.payload.get("text"), "by": session.principal},
        )

    router.freeze()
    hub = Hub(router, sweep_every=60, max_sessions=2, max_topics=2)
    return hub


@pytest.fixture
def tc(hub: Hub, monkeypatch: pytest.MonkeyPatch) -> Iterator[TestClient]:
    monkeypatch.setattr(settings, "ws_allowed_origins", ORIGIN)
    active = {ALICE, BOB}

    async def load_user(public_id: uuid.UUID):
        return SimpleNamespace(public_id=public_id) if public_id in active else None

    app.dependency_overrides[get_user_loader] = lambda: load_user
    app.dependency_overrides[get_hub] = lambda: hub
    yield TestClient(app)
    app.dependency_overrides.pop(get_user_loader, None)
    app.dependency_overrides.pop(get_hub, None)
    hub.registry.close_all()


def headers(user: uuid.UUID | None = ALICE, *, origin: str | None = ORIGIN, token=None):
    result = {}
    if origin is not None:
        result["origin"] = origin
    if token is None and user is not None:
        token = create_session_token(user)
    if token is not None:
        result["cookie"] = f"{settings.session_cookie_name}={token}"
    return result


def refused(tc: TestClient, path: str = "/api/ws", **kwargs) -> int:
    """Open a socket that must be refused; return the close code."""
    with (
        pytest.raises(WebSocketDisconnect) as exc,
        tc.websocket_connect(path, headers=headers(**kwargs)) as ws,
    ):
        ws.send_json({"type": "ping"})
        ws.receive_json()
    return exc.value.code


# ── handshake: only for an authenticated browser ──────────────────


def test_no_cookie_is_refused(tc: TestClient):
    assert refused(tc, user=None) == CloseCode.POLICY_VIOLATION


def test_tampered_token_is_refused(tc: TestClient):
    token = create_session_token(ALICE)[:-2] + "xx"

    assert refused(tc, token=token) == CloseCode.POLICY_VIOLATION


def test_token_signed_with_another_key_is_refused(tc: TestClient):
    token = jwt.encode(
        {"sub": str(ALICE), "exp": datetime.now(UTC) + timedelta(hours=1)},
        "not-the-secret-key-not-the-secret-key",
        algorithm=ALGORITHM,
    )

    assert refused(tc, token=token) == CloseCode.POLICY_VIOLATION


def test_expired_token_is_refused(tc: TestClient):
    token = jwt.encode(
        {"sub": str(ALICE), "exp": datetime.now(UTC) - timedelta(seconds=1)},
        settings.secret_key,
        algorithm=ALGORITHM,
    )

    assert refused(tc, token=token) == CloseCode.POLICY_VIOLATION


def test_token_without_expiry_is_refused(tc: TestClient):
    token = jwt.encode({"sub": str(ALICE)}, settings.secret_key, algorithm=ALGORITHM)

    assert refused(tc, token=token) == CloseCode.POLICY_VIOLATION


def test_inactive_or_deleted_user_is_refused(tc: TestClient):
    assert refused(tc, user=GONE) == CloseCode.POLICY_VIOLATION


def test_foreign_origin_is_refused_even_with_a_valid_cookie(tc: TestClient):
    assert refused(tc, origin="https://evil.test") == CloseCode.POLICY_VIOLATION


def test_missing_origin_is_refused(tc: TestClient):
    assert refused(tc, origin=None) == CloseCode.POLICY_VIOLATION


def test_origin_check_ignores_case_and_trailing_slash(tc: TestClient):
    with tc.websocket_connect(
        "/api/ws", headers=headers(origin="HTTPS://APP.test/")
    ) as ws:
        ws.send_json({"type": "ping"})
        assert ws.receive_json()["type"] == "session"


def test_refusal_does_not_create_a_session(tc: TestClient, hub: Hub):
    refused(tc, user=None)
    refused(tc, origin="https://evil.test")

    assert len(hub.registry) == 0


def test_endpoint_is_not_under_the_versioned_prefix(tc: TestClient):
    # nginx only upgrades /api/ws: a /api/v1/ws route would be unreachable
    refused(tc, path="/api/v1/ws")


def test_default_allowed_origin_is_the_proxy_origin(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(settings, "ws_allowed_origins", "")
    monkeypatch.setattr(settings, "server_name", "lb42.fr")

    monkeypatch.setattr(settings, "https_port", 8443)
    assert settings.ws_allowed_origins_set == {"https://lb42.fr:8443"}
    monkeypatch.setattr(settings, "https_port", 443)
    assert settings.ws_allowed_origins_set == {"https://lb42.fr"}


# ── once authenticated ────────────────────────────────────────────


def test_valid_session_gets_a_session_frame_first(tc: TestClient, hub: Hub):
    with tc.websocket_connect("/api/ws", headers=headers()) as ws:
        ws.send_json({"type": "ping"})
        first = ws.receive_json()
        assert first["type"] == "session"
        assert first["resumed"] is False
        assert first["reason"] == "new"
        assert ws.receive_json()["type"] == "pong"

        [session] = hub.registry.sessions()
        assert session.id == first["session"]
        assert session.principal == str(ALICE)


def test_presence_follows_the_socket(
    tc: TestClient, hub: Hub, monkeypatch: pytest.MonkeyPatch
):
    monkeypatch.setattr(realtime_topics, "_connections", realtime_topics.Counter())
    changes = []

    class Spy:
        id = "spy"

        def deliver(self, event) -> None:
            changes.append(event.payload)

    hub.broker.subscribe(PRESENCE, Spy())

    with tc.websocket_connect("/api/ws", headers=headers()) as ws:
        ws.send_json({"type": "ping"})
        assert ws.receive_json()["type"] == "session"
        assert realtime_topics._connections[str(ALICE)] == 1

    # the endpoint's finally must run on disconnect, or ALICE stays online
    assert str(ALICE) not in realtime_topics._connections
    assert changes == [
        {"user_id": str(ALICE), "status": "online"},
        {"user_id": str(ALICE), "status": "offline"},
    ]


def test_principal_is_the_user_from_the_cookie(tc: TestClient):
    with tc.websocket_connect("/api/ws", headers=headers(BOB)) as ws:
        ws.send_json(inbox(ALICE))
        assert ws.receive_json()["type"] == "session"
        error = ws.receive_json()
        assert error["code"] == "forbidden"

        ws.send_json(inbox(BOB))
        ws.send_json({"type": "ping"})
        assert ws.receive_json()["type"] == "pong"  # no error in between


def test_events_reach_the_subscriber(tc: TestClient):
    with tc.websocket_connect("/api/ws", headers=headers(ALICE)) as ws:
        ws.send_json(inbox(ALICE))
        assert ws.receive_json()["type"] == "session"

        ws.send_json(
            {
                "type": "note.send",
                "topic_kind": "inbox",
                "topic_id": str(ALICE),
                "payload": {"text": "hello"},
            }
        )
        event = ws.receive_json()
        assert event["type"] == "note.created"
        assert event["seq"] == 1
        assert event["payload"] == {"text": "hello", "by": str(ALICE)}


def test_bad_frame_answers_bad_request_without_closing(tc: TestClient):
    with tc.websocket_connect("/api/ws", headers=headers()) as ws:
        ws.send_json({"type": "ping"})
        assert ws.receive_json()["type"] == "session"
        ws.receive_json()  # pong

        ws.send_text("{not json")
        assert ws.receive_json()["code"] == "bad_request"
        ws.send_json({"type": "subscribe", "topic_kind": "inbox", "extra": 1})
        assert ws.receive_json()["code"] == "bad_request"

        ws.send_json({"type": "ping"})
        assert ws.receive_json()["type"] == "pong"


def test_oversized_frame_closes_with_message_too_big(tc: TestClient):
    with tc.websocket_connect("/api/ws", headers=headers()) as ws:
        ws.send_json({"type": "ping"})
        assert ws.receive_json()["type"] == "session"
        ws.receive_json()  # pong

        ws.send_text(
            json.dumps({"type": "ping", "pad": "x" * settings.ws_max_frame_bytes})
        )
        with pytest.raises(WebSocketDisconnect) as exc:
            ws.receive_json()
        assert exc.value.code == CloseCode.MESSAGE_TOO_BIG


def test_topic_limit_is_enforced(tc: TestClient):
    # max_topics=2 in the fixture
    with tc.websocket_connect("/api/ws", headers=headers()) as ws:
        for room in ("a", "b", "b", "c"):
            ws.send_json({"type": "subscribe", "topic_kind": "room", "topic_id": room})
        assert ws.receive_json()["type"] == "session"
        error = ws.receive_json()
        assert (error["code"], error["topic_id"]) == ("too_many_topics", "c")


def test_too_many_sessions_closes_with_try_again_later(tc: TestClient):
    # max_sessions=2 in the fixture
    with (
        tc.websocket_connect("/api/ws", headers=headers()) as one,
        tc.websocket_connect("/api/ws", headers=headers()) as two,
    ):
        for ws in (one, two):
            ws.send_json({"type": "ping"})
            assert ws.receive_json()["type"] == "session"

        with (
            pytest.raises(WebSocketDisconnect) as exc,
            tc.websocket_connect("/api/ws", headers=headers()) as three,
        ):
            three.send_json({"type": "ping"})
            three.receive_json()
        assert exc.value.code == CloseCode.TRY_AGAIN_LATER


def test_disconnect_detaches_and_resume_replays(tc: TestClient, hub: Hub):
    with tc.websocket_connect("/api/ws", headers=headers()) as ws:
        ws.send_json(inbox(ALICE))
        token = ws.receive_json()["session"]

    [session] = hub.registry.sessions()
    assert session.state == "detached"
    hub.publisher.publish(
        "note.created", Topic("inbox", str(ALICE)), {"text": "missed"}
    )

    with tc.websocket_connect("/api/ws", headers=headers()) as ws:
        ws.send_json({"type": "resume", "session": token, "last_seq": 0})
        first = ws.receive_json()
        assert first == {
            "type": "session",
            "session": token,
            "resumed": True,
            "from_seq": 1,
        }
        replayed = ws.receive_json()
        assert (replayed["seq"], replayed["payload"]) == (1, {"text": "missed"})


def test_resume_with_someone_elses_token_gets_a_fresh_session(tc: TestClient, hub: Hub):
    with tc.websocket_connect("/api/ws", headers=headers(ALICE)) as ws:
        ws.send_json(inbox(ALICE))
        alice_token = ws.receive_json()["session"]

    with tc.websocket_connect("/api/ws", headers=headers(BOB)) as ws:
        ws.send_json({"type": "resume", "session": alice_token, "last_seq": 0})
        first = ws.receive_json()
        assert first["resumed"] is False
        assert first["reason"] == "expired"
        assert first["session"] != alice_token

    alice_session = hub.registry.get(alice_token)
    assert alice_session is not None
    assert alice_session.principal == str(ALICE)


def test_socket_lives_no_longer_than_the_jwt(tc: TestClient):
    # exp is serialised in whole seconds: round first so at least 1s remains
    expires_at = datetime.now(UTC).replace(microsecond=0) + timedelta(seconds=2)
    token = jwt.encode(
        {"sub": str(ALICE), "exp": expires_at},
        settings.secret_key,
        algorithm=ALGORITHM,
    )
    with tc.websocket_connect("/api/ws", headers=headers(token=token)) as ws:
        ws.send_json({"type": "ping"})
        assert ws.receive_json()["type"] == "session"
        ws.receive_json()  # pong
        with pytest.raises(WebSocketDisconnect) as exc:
            ws.receive_json()  # nothing else comes until the token expires
        assert exc.value.code == CloseCode.REAUTH
