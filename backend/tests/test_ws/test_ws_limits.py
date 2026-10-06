"""Abuse limits of the realtime stack and the hub that assembles it:
rate limit, sessions per user, topics per session, connection lifetime."""

import asyncio
import json

import pytest
from conftest import FakeSocket, settle

from app.core.realtime.broker import Broker
from app.core.realtime.hub import Hub
from app.core.realtime.limiter import WindowLimiter
from app.core.realtime.protocol import Ping, Subscribe, parse_client_frame
from app.core.realtime.registry import Registry, TooManySessions
from app.core.realtime.router import Router, RouterError
from app.core.realtime.session import Session
from app.core.realtime.topics import Topic
from app.core.realtime.transport import CloseCode, Connection


PING = '{"type": "ping"}'


class FakeClock:
    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds


@pytest.fixture
def clock() -> FakeClock:
    return FakeClock()


@pytest.fixture
def app_router() -> Router:
    router = Router()
    router.topic("room")(lambda principal, topic: True)
    router.freeze()
    return router


def subscribe(room: str) -> Subscribe:
    return Subscribe(topic_kind="room", topic_id=room)


# ── WindowLimiter ─────────────────────────────────────────────────


def test_limiter_allows_up_to_the_limit_in_a_window(clock: FakeClock):
    limiter = WindowLimiter(3, 10.0, clock=clock)

    assert [limiter("alice", None) for _ in range(4)] == [True, True, True, False]


def test_limiter_frees_slots_as_the_window_slides(clock: FakeClock):
    limiter = WindowLimiter(2, 10.0, clock=clock)
    limiter("alice", None)
    clock.advance(5)
    limiter("alice", None)
    assert not limiter("alice", None)

    clock.advance(5)  # the first hit leaves the window

    assert limiter("alice", None)
    assert not limiter("alice", None)


def test_limiter_counts_each_principal_apart(clock: FakeClock):
    limiter = WindowLimiter(1, 10.0, clock=clock)

    assert limiter("alice", None)
    assert limiter("bob", None)
    assert not limiter("alice", None)


def test_limiter_forgets_idle_principals(clock: FakeClock):
    limiter = WindowLimiter(1, 10.0, clock=clock)
    limiter("alice", None)
    clock.advance(4)
    limiter("bob", None)
    clock.advance(6)

    assert limiter.forget_idle() == 1  # alice only, bob is still in his window
    assert not limiter("bob", None)


@pytest.mark.parametrize(("limit", "window"), [(0, 10.0), (1, 0.0)])
def test_limiter_rejects_nonsense_settings(limit: int, window: float):
    with pytest.raises(ValueError):
        WindowLimiter(limit, window)


def test_session_answers_rate_limited_past_the_limit(
    app_router: Router, broker: Broker, clock: FakeClock
):
    registry = Registry(
        app_router, broker, clock=clock, limiter=WindowLimiter(2, 10.0, clock=clock)
    )
    session = registry.start("alice")
    session.drain()

    for _ in range(3):
        session.handle(Ping())

    assert [f.type for f in session.drain()] == ["pong", "pong", "error"]


def test_invalid_frames_count_against_the_limit(app_router: Router, broker: Broker):
    session = Session("s", "alice", app_router, broker, limiter=WindowLimiter(2, 10.0))
    session.hello()
    session.drain()

    for _ in range(3):
        session.handle(parse_client_frame("{not json"))

    assert [f.code for f in session.drain()] == ["bad_request", "bad_request", "rate_limited"]

# ── sessions per principal ────────────────────────────────────────


def test_start_refuses_past_the_limit_of_attached_sessions(
    app_router: Router, broker: Broker, clock: FakeClock
):
    registry = Registry(app_router, broker, clock=clock, max_sessions=2)
    registry.start("alice")
    registry.start("alice")

    with pytest.raises(TooManySessions):
        registry.start("alice")
    assert len(registry.sessions_of("alice")) == 2


def test_limit_is_per_principal(app_router: Router, broker: Broker, clock: FakeClock):
    registry = Registry(app_router, broker, clock=clock, max_sessions=1)
    registry.start("alice")

    assert registry.start("bob").principal == "bob"


def test_start_evicts_the_longest_idle_detached_session(
    app_router: Router, broker: Broker, clock: FakeClock
):
    registry = Registry(app_router, broker, clock=clock, max_sessions=2)
    oldest = registry.start("alice")
    oldest.handle(subscribe("a"))
    clock.advance(5)
    newer = registry.start("alice")
    oldest.detach()
    newer.detach()

    fresh = registry.start("alice")

    assert oldest.closed
    assert oldest.id not in registry
    assert broker.topics(oldest) == frozenset()
    assert not newer.closed
    assert {s.id for s in registry.sessions_of("alice")} == {newer.id, fresh.id}


def test_resume_of_an_expired_token_is_also_bounded(
    app_router: Router, broker: Broker, clock: FakeClock
):
    registry = Registry(app_router, broker, clock=clock, max_sessions=1)
    registry.start("alice")

    with pytest.raises(TooManySessions):
        registry.resume("unknown-token", "alice", 0)


async def test_connection_past_the_limit_is_closed_with_try_again_later(
    app_router: Router, broker: Broker
):
    registry = Registry(app_router, broker, max_sessions=1)
    registry.start("alice")
    socket = FakeSocket(PING)

    code = await asyncio.wait_for(Connection(socket, registry, "alice").run(), 1)

    assert code == CloseCode.TRY_AGAIN_LATER
    assert socket.closed_with == (CloseCode.TRY_AGAIN_LATER, "too many sessions")
    assert socket.sent == []
    assert len(registry.sessions_of("alice")) == 1


# ── topics per session ────────────────────────────────────────────


def test_subscribe_past_the_topic_limit_is_refused(
    app_router: Router, broker: Broker, clock: FakeClock
):
    registry = Registry(app_router, broker, clock=clock, max_topics=2)
    session = registry.start("alice")
    session.drain()

    for room in ("a", "b", "c"):
        session.handle(subscribe(room))

    [error] = session.drain()
    assert error.type == "error"
    assert error.code == "too_many_topics"
    assert error.topic_id == "c"
    assert len(session.topics()) == 2


def test_resubscribing_at_the_limit_is_not_an_error(
    app_router: Router, broker: Broker, clock: FakeClock
):
    registry = Registry(app_router, broker, clock=clock, max_topics=1)
    session = registry.start("alice")
    session.handle(subscribe("a"))
    session.drain()

    session.handle(subscribe("a"))

    assert session.drain() == []


def test_unsubscribing_frees_a_topic_slot(
    app_router: Router, broker: Broker, clock: FakeClock
):
    registry = Registry(app_router, broker, clock=clock, max_topics=1)
    session = registry.start("alice")
    session.handle(subscribe("a"))
    session.handle(
        parse_client_frame(
            json.dumps({"type": "unsubscribe", "topic_kind": "room", "topic_id": "a"})
        )
    )
    session.handle(subscribe("b"))

    assert [f.type for f in session.drain()] == ["session"]
    assert {t.id for t in session.topics()} == {"b"}


# ── connection lifetime ───────────────────────────────────────────


async def test_connection_closes_once_its_lifetime_is_spent(
    app_router: Router, broker: Broker
):
    registry = Registry(app_router, broker)
    socket = FakeSocket(PING)

    code = await asyncio.wait_for(
        Connection(socket, registry, "alice", tick=0.01, lifetime=0.05).run(), 1
    )

    assert code == CloseCode.REAUTH
    assert socket.closed_with == (CloseCode.REAUTH, "expired")
    assert socket.types() == ["session", "pong"]
    # Detached, not closed: logging in again as the same user can resume it
    [session] = registry.sessions()
    assert session.state == "detached"


async def test_connection_without_lifetime_does_not_expire(
    app_router: Router, broker: Broker
):
    registry = Registry(app_router, broker)
    socket = FakeSocket(PING)
    task = asyncio.create_task(Connection(socket, registry, "alice", tick=0.01).run())

    await asyncio.sleep(0.05)

    assert not task.done()
    socket.hang_up()
    assert await asyncio.wait_for(task, 1) == CloseCode.GOING_AWAY


# ── Hub ───────────────────────────────────────────────────────────


async def test_hub_start_checks_and_freezes_the_router():
    router = Router()
    hub = Hub(router, sweep_every=60)

    await hub.start()
    try:
        assert router.frozen
        with pytest.raises(RouterError):
            router.topic("late")
    finally:
        await hub.stop()


async def test_hub_start_refuses_an_on_subscribe_without_authorizer():
    router = Router()
    router.on_subscribe("orphan")(lambda session, topic: [])

    with pytest.raises(RouterError):
        await Hub(router).start()


async def test_hub_stop_closes_every_session():
    router = Router()
    router.topic("room")(lambda principal, topic: True)
    hub = Hub(router, sweep_every=60)
    await hub.start()
    session = hub.registry.start("alice")
    session.handle(subscribe("a"))

    await hub.stop()

    assert session.closed
    assert len(hub.registry) == 0
    assert len(hub.broker) == 0


async def test_hub_sweeper_runs_in_the_background(clock: FakeClock):
    router = Router()
    hub = Hub(router, sweep_every=0.01, ttl=30, clock=clock)
    await hub.start()
    try:
        session = hub.registry.start("alice")
        session.detach()
        clock.advance(31)
        await asyncio.sleep(0.05)
        await settle()

        assert session.closed
        assert len(hub.registry) == 0
    finally:
        await hub.stop()


async def test_hub_publisher_reaches_subscribed_sessions():
    router = Router()
    router.topic("room")(lambda principal, topic: True)
    hub = Hub(router, sweep_every=60)
    await hub.start()
    try:
        session = hub.registry.start("alice")
        session.handle(subscribe("a"))
        session.drain()

        assert hub.publisher.publish("hello", Topic("room", "a"), {"x": 1}) == 1
        [event] = session.drain()
        assert (event.type, event.seq, event.payload) == ("hello", 1, {"x": 1})
    finally:
        await hub.stop()
