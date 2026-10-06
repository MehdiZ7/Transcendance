"""Unit tests for registry.py: tokens, TTL, resume, takeover."""

import itertools

import pytest

from app.core.realtime.broker import Broker
from app.core.realtime.protocol import EventFrame, SessionFrame, Subscribe
from app.core.realtime.registry import Registry
from app.core.realtime.router import Router
from app.core.realtime.topics import Topic

CONVERSATION = Topic("conversation", "42")


class FakeClock:
    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds


def event(text: str = "salut") -> EventFrame:
    return EventFrame(
        type="message.created",
        topic_kind="conversation",
        topic_id="42",
        payload={"text": text},
    )


@pytest.fixture
def clock() -> FakeClock:
    return FakeClock()


@pytest.fixture
def app_router() -> Router:
    router = Router()
    router.topic("conversation")(lambda principal, topic: True)
    router.freeze()
    return router


@pytest.fixture
def registry(app_router: Router, broker: Broker, clock: FakeClock) -> Registry:
    counter = itertools.count(1)
    return Registry(
        app_router,
        broker,
        ttl=30,
        clock=clock,
        replay_limit=5,
        token_factory=lambda: f"tok-{next(counter)}",
    )


# ── creating sessions ─────────────────────────────────────────────


def test_start_returns_an_attached_greeted_session(registry: Registry):
    session = registry.start("alice")

    assert session.attached
    frame = session.drain()[0]
    assert isinstance(frame, SessionFrame)
    assert (frame.resumed, frame.reason) == (False, "new")


def test_started_session_is_registered(registry: Registry):
    session = registry.start("alice")

    assert registry.get(session.id) is session
    assert session.id in registry
    assert len(registry) == 1


def test_tokens_are_unique(registry: Registry):
    tokens = {registry.start("alice").id for _ in range(5)}

    assert len(tokens) == 5
    assert len(registry) == 5


def test_token_collision_is_retried(app_router: Router, broker: Broker):
    tokens = iter(["same", "same", "other"])
    registry = Registry(app_router, broker, token_factory=lambda: next(tokens))

    first = registry.start("alice")
    second = registry.start("bob")

    assert (first.id, second.id) == ("same", "other")


def test_endless_collisions_raise(app_router: Router, broker: Broker):
    registry = Registry(app_router, broker, token_factory=lambda: "same")
    registry.start("alice")

    with pytest.raises(RuntimeError, match="collid"):
        registry.start("bob")


# ── resume ────────────────────────────────────────────────────────


def test_resume_returns_the_same_session(registry: Registry):
    session = registry.start("alice")
    session.drain()
    registry.detach(session)

    resumed = registry.resume(session.id, "alice", last_seq=0)

    assert resumed is session
    assert resumed.attached
    assert resumed.drain()[0].resumed is True


def test_resume_replays_events(registry: Registry):
    session = registry.start("alice")
    session.drain()
    registry.detach(session)
    session.deliver(event("pendant"))

    registry.resume(session.id, "alice", last_seq=0)

    frames = session.drain()
    assert [type(f).__name__ for f in frames] == ["SessionFrame", "EventFrame"]
    assert frames[1].payload["text"] == "pendant"


def test_unknown_token_yields_a_new_session(registry: Registry):
    session = registry.resume("nope", "alice", last_seq=3)

    assert session.id != "nope"
    frame = session.drain()[0]
    assert (frame.resumed, frame.reason) == (False, "expired")


def test_resume_of_another_principal_is_refused(registry: Registry):
    session = registry.start("alice")
    session.drain()
    registry.detach(session)

    stolen = registry.resume(session.id, "mallory", last_seq=0)

    assert stolen is not session
    assert stolen.principal == "mallory"
    assert stolen.drain()[0].reason == "expired"
    assert registry.get(session.id) is session  # alice's session untouched


def test_resume_of_an_attached_session_takes_over(registry: Registry):
    session = registry.start("alice")
    session.drain()

    resumed = registry.resume(session.id, "alice", last_seq=0)

    assert resumed is session
    assert session.attached
    assert session.drain()[0].resumed is True


def test_takeover_keeps_subscriptions(registry: Registry, broker: Broker):
    session = registry.start("alice")
    session.handle(Subscribe(topic_kind="conversation", topic_id="42"))
    session.drain()

    registry.resume(session.id, "alice", last_seq=0)

    assert broker.subscribers(CONVERSATION) == {session}


def test_resume_past_the_replay_buffer_starts_over(registry: Registry):
    session = registry.start("alice")
    session.drain()
    for i in range(8):  # replay_limit is 5
        session.deliver(event(str(i)))
        session.drain()
    registry.detach(session)

    resumed = registry.resume(session.id, "alice", last_seq=1)

    assert resumed is session  # same token, fresh stream
    frame = session.drain()[0]
    assert (frame.resumed, frame.reason) == (False, "gap")


# ── expiry ────────────────────────────────────────────────────────


def test_detached_session_survives_within_the_ttl(
    registry: Registry, clock: FakeClock
):
    session = registry.start("alice")
    registry.detach(session)

    clock.advance(29)

    assert registry.get(session.id) is session


def test_detached_session_expires_after_the_ttl(registry: Registry, clock: FakeClock):
    session = registry.start("alice")
    registry.detach(session)

    clock.advance(31)

    assert registry.get(session.id) is None
    assert session.closed
    assert len(registry) == 0


def test_expired_session_leaves_the_broker(
    registry: Registry, broker: Broker, clock: FakeClock
):
    session = registry.start("alice")
    session.handle(Subscribe(topic_kind="conversation", topic_id="42"))
    registry.detach(session)

    clock.advance(31)
    registry.get(session.id)

    assert broker.subscribers(CONVERSATION) == frozenset()


def test_resume_after_expiry_yields_a_new_session(
    registry: Registry, clock: FakeClock
):
    session = registry.start("alice")
    registry.detach(session)
    clock.advance(31)

    replacement = registry.resume(session.id, "alice", last_seq=2)

    assert replacement is not session
    assert replacement.drain()[0].reason == "expired"


def test_attached_session_never_expires(registry: Registry, clock: FakeClock):
    session = registry.start("alice")

    clock.advance(10_000)

    assert registry.get(session.id) is session


def test_client_activity_postpones_expiry(registry: Registry, clock: FakeClock):
    session = registry.start("alice")
    registry.detach(session)
    clock.advance(20)
    session.touch()

    clock.advance(20)

    assert registry.get(session.id) is session


def test_sweep_evicts_expired_sessions(registry: Registry, clock: FakeClock):
    stale = registry.start("alice")
    registry.detach(stale)
    fresh = registry.start("bob")
    clock.advance(31)

    assert registry.sweep() == 1

    assert registry.tokens() == {fresh.id}
    assert stale.closed


def test_sweep_is_harmless_when_nothing_expired(registry: Registry):
    registry.start("alice")

    assert registry.sweep() == 0
    assert len(registry) == 1


def test_sweep_collects_closed_sessions(registry: Registry):
    session = registry.start("alice")
    session.close()  # closed behind the registry's back

    assert registry.sweep() == 1
    assert len(registry) == 0


# ── closing ───────────────────────────────────────────────────────


def test_close_forgets_the_token(registry: Registry, broker: Broker):
    session = registry.start("alice")
    session.handle(Subscribe(topic_kind="conversation", topic_id="42"))

    registry.close(session)

    assert registry.get(session.id) is None
    assert session.closed
    assert len(broker) == 0


def test_resume_of_a_closed_session_yields_a_new_one(registry: Registry):
    session = registry.start("alice")
    registry.close(session)

    replacement = registry.resume(session.id, "alice", last_seq=0)

    assert replacement is not session
    assert replacement.drain()[0].reason == "expired"


def test_close_all(registry: Registry, broker: Broker):
    sessions = [registry.start(name) for name in ("alice", "bob")]

    registry.close_all()

    assert len(registry) == 0
    assert all(s.closed for s in sessions)


def test_detach_keeps_the_token(registry: Registry):
    session = registry.start("alice")

    registry.detach(session)

    assert registry.get(session.id) is session
    assert not session.attached