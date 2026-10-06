"""Unit tests for transport.py, driven by an in-memory socket.

FakeSocket (conftest) replaces the WebSocket library: a queue of inbound
frames, a list of outbound ones. A connection either runs to the end on a
script that hangs up, or runs as a task that the test drives with `settle`.
"""

import asyncio
import json

import pytest

from app.core.realtime.broker import Broker
from app.core.realtime.protocol import EventFrame
from app.core.realtime.registry import Registry
from app.core.realtime.router import Router
from app.core.realtime.topics import Topic
from app.core.realtime.transport import CloseCode, Connection, ConnectionClosed
from conftest import FakeSocket, settle

CONVERSATION = Topic("conversation", "42")

SUBSCRIBE = json.dumps(
    {"type": "subscribe", "topic_kind": "conversation", "topic_id": "42"}
)
PING = '{"type": "ping"}'


class FakeClock:
    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds


def created() -> EventFrame:
    return EventFrame(type="message.created", topic_kind="conversation", topic_id="42")


@pytest.fixture
def clock() -> FakeClock:
    return FakeClock()


@pytest.fixture
def app_router() -> Router:
    router = Router()
    router.topic("conversation")(lambda principal, topic: topic.id == "42")
    router.freeze()
    return router


@pytest.fixture
def registry(app_router: Router, broker: Broker, clock: FakeClock) -> Registry:
    return Registry(app_router, broker, ttl=30, clock=clock, queue_limit=3)


def connect(socket: FakeSocket, registry: Registry, **kwargs) -> Connection:
    kwargs.setdefault("tick", 0.01)
    kwargs.setdefault("handshake_timeout", 0.05)
    return Connection(socket, registry, "alice", **kwargs)


async def finish(task: asyncio.Task[int]) -> int:
    return await asyncio.wait_for(task, timeout=1)


# ── handshake ─────────────────────────────────────────────────────


async def test_first_frame_opens_a_session(registry: Registry):
    socket = FakeSocket(PING, hang_up=True)

    await connect(socket, registry).run()

    assert socket.types()[:2] == ["session", "pong"]
    assert socket.first("session")["resumed"] is False


async def test_silent_client_is_closed(registry: Registry):
    socket = FakeSocket()

    code = await connect(socket, registry).run()

    assert code == CloseCode.POLICY_VIOLATION
    assert socket.closed_with == (CloseCode.POLICY_VIOLATION, "no handshake")
    assert len(registry) == 0


async def test_resume_as_first_frame_reattaches(registry: Registry):
    existing = registry.start("alice")
    existing.drain()
    registry.detach(existing)
    existing.deliver(EventFrame(type="message.created", topic_kind="conversation"))
    socket = FakeSocket(
        json.dumps({"type": "resume", "session": existing.id, "last_seq": 0}),
        hang_up=True,
    )

    await connect(socket, registry).run()

    assert socket.first("session")["resumed"] is True
    assert socket.types() == ["session", "message.created"]


async def test_resume_with_an_unknown_token_opens_a_new_session(registry: Registry):
    socket = FakeSocket(
        json.dumps({"type": "resume", "session": "nope", "last_seq": 5}),
        hang_up=True,
    )

    await connect(socket, registry).run()

    assert socket.first("session")["reason"] == "expired"


async def test_bad_first_frame_still_opens_a_session(registry: Registry):
    socket = FakeSocket("not json", hang_up=True)

    await connect(socket, registry).run()

    assert socket.types() == ["session", "error"]
    assert socket.sent[1]["code"] == "bad_request"


# ── the loop ──────────────────────────────────────────────────────


async def test_frames_are_forwarded_to_the_session(registry: Registry):
    socket = FakeSocket(SUBSCRIBE, PING, hang_up=True)

    connection = connect(socket, registry)
    await connection.run()

    assert socket.types() == ["session", "pong"]
    assert connection.session is not None


async def test_published_event_is_sent_without_waiting_for_a_tick(
    registry: Registry, broker: Broker
):
    socket = FakeSocket(SUBSCRIBE)
    # A tick far longer than the test: only the wake-up can flush the event
    task = asyncio.create_task(connect(socket, registry, tick=60).run())
    await settle()

    broker.publish(created())
    await settle()

    assert socket.types() == ["session", "message.created"]
    assert socket.first("message.created")["seq"] == 1
    socket.hang_up()
    assert await finish(task) == CloseCode.GOING_AWAY


async def test_frames_sent_later_are_answered(registry: Registry):
    socket = FakeSocket(SUBSCRIBE)
    task = asyncio.create_task(connect(socket, registry, tick=60).run())
    await settle()

    socket.feed(PING)
    await settle()

    assert socket.types() == ["session", "pong"]
    socket.hang_up()
    await finish(task)


async def test_errors_do_not_end_the_connection(registry: Registry):
    socket = FakeSocket("not json", SUBSCRIBE, PING, hang_up=True)

    await connect(socket, registry).run()

    assert socket.types() == ["session", "error", "pong"]


# ── closing ───────────────────────────────────────────────────────


async def test_peer_disconnection_keeps_the_session(registry: Registry):
    socket = FakeSocket(SUBSCRIBE, hang_up=True)

    connection = connect(socket, registry)
    code = await connection.run()

    assert code == CloseCode.GOING_AWAY
    assert connection.session is not None
    assert not connection.session.attached
    assert registry.get(connection.session.id) is connection.session


async def test_idle_client_is_closed(registry: Registry, clock: FakeClock):
    socket = FakeSocket(PING)
    task = asyncio.create_task(connect(socket, registry, idle_timeout=60).run())
    await settle()

    clock.advance(61)

    assert await finish(task) == CloseCode.GOING_AWAY
    assert socket.closed_with == (CloseCode.GOING_AWAY, "idle")


async def test_burst_gaps_the_session_and_closes_for_retry(
    registry: Registry, broker: Broker
):
    socket = FakeSocket(SUBSCRIBE)
    connection = connect(socket, registry)
    task = asyncio.create_task(connection.run())
    await settle()

    for _ in range(10):  # queue_limit is 3, no chance to flush in between
        broker.publish(created())

    assert await finish(task) == CloseCode.TRY_AGAIN_LATER
    assert socket.closed_with == (CloseCode.TRY_AGAIN_LATER, "gap")
    assert connection.session is not None
    assert connection.session.gapped


async def test_client_that_stops_reading_is_gapped(registry: Registry, broker: Broker):
    socket = FakeSocket(SUBSCRIBE)
    task = asyncio.create_task(connect(socket, registry).run())
    await settle()
    socket.gate.clear()  # sends now block

    for _ in range(10):
        broker.publish(created())
        await settle()
    socket.gate.set()

    assert await finish(task) == CloseCode.TRY_AGAIN_LATER


async def test_closing_the_principal_hangs_up_with_reauth(registry: Registry):
    # Logout or suspension. The client frame racing the close used to reach
    # a closed session and crash the connection into 1011.
    socket = FakeSocket(SUBSCRIBE)
    task = asyncio.create_task(connect(socket, registry).run())
    await settle()

    assert registry.close_principal("alice") == 1
    socket.feed(PING)

    assert await finish(task) == CloseCode.REAUTH
    assert socket.closed_with == (CloseCode.REAUTH, "revoked")
    assert len(registry) == 0


async def test_cancelled_connection_detaches_the_session(registry: Registry):
    socket = FakeSocket(SUBSCRIBE)
    connection = connect(socket, registry)
    task = asyncio.create_task(connection.run())
    await settle()

    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task

    assert connection.session is not None
    assert not connection.session.attached
    assert registry.get(connection.session.id) is connection.session


async def test_finished_connection_stops_listening(registry: Registry, broker: Broker):
    socket = FakeSocket(SUBSCRIBE, hang_up=True)
    connection = connect(socket, registry)
    await connection.run()
    assert connection.session is not None
    connection._wake.clear()

    registry.resume(connection.session.id, "alice", 0)
    broker.publish(created())

    assert not connection._wake.is_set()


# ── takeover ──────────────────────────────────────────────────────


def resume(token: str, last_seq: int = 0) -> str:
    return json.dumps({"type": "resume", "session": token, "last_seq": last_seq})


async def start_old(registry: Registry) -> tuple[FakeSocket, Connection, asyncio.Task]:
    """A connection whose socket went half-open: it runs, but its client
    already reconnected elsewhere. A long tick: only a wake-up can end it."""
    socket = FakeSocket(SUBSCRIBE)
    connection = connect(socket, registry, tick=60)
    task = asyncio.create_task(connection.run())
    await settle()
    return socket, connection, task


async def test_takeover_closes_the_old_connection(registry: Registry):
    old_socket, old, old_task = await start_old(registry)
    assert old.session is not None
    token = old.session.id

    new_socket = FakeSocket(resume(token))
    new = connect(new_socket, registry)
    new_task = asyncio.create_task(new.run())

    assert await finish(old_task) == CloseCode.REPLACED
    assert old_socket.closed_with == (CloseCode.REPLACED, "replaced")
    assert not old.owns_session
    # the session is the newcomer's, still attached
    assert new.session is old.session
    assert new.session.attached
    assert registry.get(token) is new.session
    assert new_socket.first("session")["resumed"] is True

    new_socket.hang_up()
    await finish(new_task)


async def test_old_connection_does_not_steal_events(registry: Registry, broker: Broker):
    old_socket, old, _ = await start_old(registry)
    assert old.session is not None
    new_socket = FakeSocket(resume(old.session.id))
    new_task = asyncio.create_task(connect(new_socket, registry).run())
    await settle()

    broker.publish(created())
    await settle()

    assert "message.created" not in old_socket.types()
    assert new_socket.types() == ["session", "message.created"]
    new_socket.hang_up()
    await finish(new_task)


async def test_old_socket_frames_are_ignored_after_takeover(registry: Registry):
    old_socket, old, old_task = await start_old(registry)
    assert old.session is not None
    new_socket = FakeSocket(resume(old.session.id))

    # The newcomer's handshake runs first, then the old reader gets the ping
    new_task = asyncio.create_task(connect(new_socket, registry).run())
    old_socket.feed(PING)
    await settle()

    assert "pong" not in old_socket.types()
    assert "pong" not in new_socket.types()
    await finish(old_task)
    new_socket.hang_up()
    await finish(new_task)


async def test_takeover_during_a_send(registry: Registry, broker: Broker):
    old_socket, old, old_task = await start_old(registry)
    assert old.session is not None
    old_socket.gate.clear()
    broker.publish(created())  # the old writer blocks sending it
    await settle()

    new_socket = FakeSocket(resume(old.session.id, 1))
    new = connect(new_socket, registry)
    new_task = asyncio.create_task(new.run())
    await settle()
    old_socket.gate.set()  # the stuck send completes after the takeover

    assert await finish(old_task) == CloseCode.REPLACED
    assert new.session is not None and new.session.attached
    broker.publish(created())
    await settle()
    assert [f["seq"] for f in new_socket.sent if f["type"] == "message.created"] == [2]
    new_socket.hang_up()
    await finish(new_task)


async def test_replaced_connection_cannot_close_the_session(registry: Registry):
    old_socket, old, old_task = await start_old(registry)
    assert old.session is not None
    new_socket = FakeSocket(resume(old.session.id))
    new_task = asyncio.create_task(connect(new_socket, registry).run())
    await finish(old_task)

    await old.close()

    assert old.session.attached
    assert len(registry) == 1
    new_socket.hang_up()
    await finish(new_task)


async def test_close_forgets_the_session(registry: Registry):
    socket = FakeSocket(SUBSCRIBE)
    connection = connect(socket, registry)
    await connection.open()
    session = connection.session

    code = await connection.close()

    assert code == CloseCode.NORMAL
    assert session is not None and session.closed
    assert len(registry) == 0


async def test_send_failure_is_survived(registry: Registry):
    class DeadSocket(FakeSocket):
        async def send(self, raw: str) -> None:
            raise ConnectionClosed("peer gone")

    socket = DeadSocket(PING)
    connection = connect(socket, registry)

    code = await connection.run()

    assert code == CloseCode.GOING_AWAY
    assert connection.session is not None
    assert not connection.session.attached


async def test_internal_error_is_reported(registry: Registry):
    class ExplodingSocket(FakeSocket):
        calls = 0

        async def receive(self) -> str:
            self.calls += 1
            if self.calls > 1:
                raise RuntimeError("boom")
            return await super().receive()

    socket = ExplodingSocket(PING)

    code = await connect(socket, registry).run()

    assert code == CloseCode.INTERNAL_ERROR
    assert socket.closed_with == (CloseCode.INTERNAL_ERROR, "internal error")


async def test_close_is_not_called_twice(registry: Registry):
    socket = FakeSocket()
    connection = connect(socket, registry)
    await connection.run()

    await connection.close(CloseCode.NORMAL)

    assert socket.closed_with == (CloseCode.POLICY_VIOLATION, "no handshake")
