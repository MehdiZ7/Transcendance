"""Unit tests for session.py: queue, seq, replay, lifecycle.

Time is injected, the queue lives in memory, nothing is async: every case
below is deterministic and runs without a socket.
"""

import pytest

from app.core.realtime.broker import Broker
from app.core.realtime.protocol import (
    ClientMessage,
    ErrorFrame,
    EventFrame,
    Ping,
    PongFrame,
    Resume,
    SessionFrame,
    Subscribe,
    Unsubscribe,
    parse_server_frame,
)
from app.core.realtime.router import Router
from app.core.realtime.session import Session
from app.core.realtime.topics import Topic

CONVERSATION = Topic("conversation", "42")
SECRET = Topic("secret", "1")


class FakeClock:
    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds


def event(text: str = "salut", topic: Topic = CONVERSATION) -> EventFrame:
    return EventFrame(
        type="message.created",
        topic_kind=topic.kind,
        topic_id=topic.id,
        payload={"text": text},
    )


@pytest.fixture
def clock() -> FakeClock:
    return FakeClock()


@pytest.fixture
def open_router() -> Router:
    router = Router()
    router.topic("conversation")(lambda principal, topic: principal == "alice")
    router.message("message.create")(lambda session, frame: None)
    router.freeze()
    return router


@pytest.fixture
def session(broker: Broker, open_router: Router, clock: FakeClock) -> Session:
    s = Session(
        "tok",
        "alice",
        open_router,
        broker,
        queue_limit=4,
        replay_limit=3,
        clock=clock,
    )
    s.hello()
    s.drain()
    return s


# ── handshake and lifecycle ───────────────────────────────────────


def test_hello_sends_a_new_session_frame(
    broker: Broker, open_router: Router, clock: FakeClock
):
    session = Session("tok", "alice", open_router, broker, clock=clock)

    session.hello()

    frame = session.drain()[0]
    assert isinstance(frame, SessionFrame)
    assert (frame.session, frame.resumed, frame.reason) == ("tok", False, "new")
    assert session.attached


def test_session_starts_detached(broker: Broker, open_router: Router):
    assert not Session("tok", "alice", open_router, broker).attached


def test_detach_keeps_the_session_alive(session: Session):
    session.detach()

    assert not session.attached
    assert not session.closed


def test_detach_drops_queued_frames(session: Session):
    session.deliver(event())
    session.detach()

    assert session.pending == 0


def test_close_drops_subscriptions(session: Session, broker: Broker):
    session.handle(Subscribe(topic_kind="conversation", topic_id="42"))

    session.close()

    assert session.closed
    assert broker.topics(session) == frozenset()
    assert session.pending == 0


def test_close_is_idempotent(session: Session):
    session.close()
    session.close()

    assert session.closed


def test_handle_after_close_raises(session: Session):
    session.close()

    with pytest.raises(RuntimeError, match="closed"):
        session.handle(Ping())


def test_deliver_after_close_is_ignored(session: Session):
    session.close()

    session.deliver(event())

    assert session.pending == 0


# ── numbering ─────────────────────────────────────────────────────


def test_seq_starts_at_one_and_increments(session: Session):
    session.deliver(event("un"))
    session.deliver(event("deux"))

    assert [f.seq for f in session.drain()] == [1, 2]
    assert session.last_seq == 2


def test_deliver_does_not_mutate_the_published_event(session: Session):
    published = event()

    session.deliver(published)

    assert published.seq is None
    assert session.drain()[0].seq == 1


def test_seq_keeps_counting_while_detached(session: Session):
    session.deliver(event("un"))
    session.detach()
    session.deliver(event("deux"))

    assert session.last_seq == 2
    assert session.pending == 0  # nothing queued while detached


# ── outbound queue and gaps ───────────────────────────────────────


def test_queue_accumulates_until_drained(session: Session):
    session.deliver(event("un"))
    session.deliver(event("deux"))

    assert session.pending == 2
    assert len(session.drain()) == 2
    assert session.pending == 0


def test_overflow_marks_a_gap(session: Session):
    for i in range(10):  # queue_limit is 4
        session.deliver(event(str(i)))

    assert session.gapped
    assert session.should_close
    assert session.pending == 4


def test_gapped_session_stops_delivering(session: Session):
    for i in range(10):
        session.deliver(event(str(i)))
    seq_at_gap = session.last_seq

    session.deliver(event("after"))

    assert session.last_seq == seq_at_gap


def test_no_gap_when_the_transport_keeps_up(session: Session):
    for i in range(10):
        session.deliver(event(str(i)))
        session.drain()

    assert not session.gapped
    assert session.last_seq == 10


def test_drain_json_serializes(session: Session):
    session.deliver(event())

    raw = session.drain_json()

    assert len(raw) == 1
    assert parse_server_frame(raw[0]).seq == 1


# ── listener ──────────────────────────────────────────────────────


def test_listener_is_called_for_every_queued_frame(session: Session):
    calls: list[int] = []
    session.listen(lambda: calls.append(session.pending))

    session.deliver(event("un"))
    session.handle(Ping())

    assert calls == [1, 2]


def test_detach_wakes_the_listener(session: Session):
    calls: list[bool] = []
    session.listen(lambda: calls.append(session.attached))

    session.detach()

    assert calls == [False]


def test_listener_is_not_called_while_detached(session: Session):
    calls: list[None] = []
    session.detach()
    session.listen(lambda: calls.append(None))

    session.deliver(event())

    assert calls == []


# ── epoch ─────────────────────────────────────────────────────────


def test_hello_starts_the_first_epoch(session: Session):
    assert session.epoch == 1


def test_every_resume_bumps_the_epoch(session: Session):
    session.detach()
    session.resume(0)
    session.detach()
    session.resume(99)  # refused (gap), still a new attachment

    assert session.epoch == 3


def test_detach_keeps_the_epoch(session: Session):
    session.detach()

    assert session.epoch == 1


def test_listener_is_called_on_gap(session: Session):
    calls: list[bool] = []
    for i in range(4):  # fill the queue, queue_limit is 4
        session.deliver(event(str(i)))
    session.listen(lambda: calls.append(session.gapped))

    session.deliver(event("overflow"))

    assert calls == [True]


def test_unlisten_ignores_a_stale_listener(session: Session):
    calls: list[str] = []

    def old() -> None:
        calls.append("old")

    def new() -> None:
        calls.append("new")

    session.listen(old)
    session.listen(new)  # takeover
    session.unlisten(old)
    session.deliver(event())

    assert calls == ["new"]


def test_unlisten_removes_the_current_listener(session: Session):
    calls: list[None] = []

    def listener() -> None:
        calls.append(None)

    session.listen(listener)
    session.unlisten(listener)
    session.deliver(event())

    assert calls == []


# ── resume ────────────────────────────────────────────────────────


def test_resume_replays_what_the_client_missed(session: Session):
    session.deliver(event("un"))
    session.drain()
    session.detach()
    session.deliver(event("deux"))
    session.deliver(event("trois"))

    assert session.resume(last_seq=1) is True

    frames = session.drain()
    assert isinstance(frames[0], SessionFrame)
    assert (frames[0].resumed, frames[0].from_seq) == (True, 2)
    assert [f.seq for f in frames[1:]] == [2, 3]
    assert [f.payload["text"] for f in frames[1:]] == ["deux", "trois"]


def test_resume_with_nothing_missed(session: Session):
    session.deliver(event("un"))
    session.drain()
    session.detach()

    assert session.resume(last_seq=1) is True
    assert len(session.drain()) == 1  # just the session frame


def test_resume_beyond_the_replay_buffer_is_a_gap(session: Session):
    for i in range(5):  # replay_limit is 3
        session.deliver(event(str(i)))
        session.drain()
    session.detach()

    assert session.resume(last_seq=1) is False

    frame = session.drain()[0]
    assert (frame.resumed, frame.reason) == (False, "gap")


def test_resume_of_a_gapped_session_is_refused(session: Session):
    for i in range(10):
        session.deliver(event(str(i)))
    session.detach()

    assert session.resume(last_seq=1) is False
    assert session.drain()[0].reason == "gap"


def test_failed_resume_resets_the_session(session: Session, broker: Broker):
    session.handle(Subscribe(topic_kind="conversation", topic_id="42"))
    for i in range(10):
        session.deliver(event(str(i)))
    session.detach()

    session.resume(last_seq=1)

    assert session.last_seq == 0
    assert not session.gapped
    assert broker.topics(session) == frozenset()


def test_client_ahead_of_the_server_is_a_gap(session: Session):
    session.deliver(event())
    session.drain()
    session.detach()

    assert session.resume(last_seq=99) is False
    assert session.drain()[0].reason == "gap"


def test_resume_reattaches(session: Session):
    session.detach()

    session.resume(last_seq=0)

    assert session.attached


def test_resume_while_attached_raises(session: Session):
    with pytest.raises(RuntimeError, match="attached"):
        session.resume(last_seq=0)


def test_resume_that_would_overflow_the_queue_is_a_gap(
    broker: Broker, open_router: Router, clock: FakeClock
):
    session = Session(
        "tok", "alice", open_router, broker, queue_limit=3, replay_limit=10, clock=clock
    )
    for i in range(5):  # detached from the start: all kept for replay
        session.deliver(event(str(i)))

    assert session.resume(last_seq=0) is False

    frames = session.drain()
    assert len(frames) == 1
    assert (frames[0].resumed, frames[0].reason) == (False, "gap")
    assert not session.gapped


def test_resume_that_exactly_fills_the_queue_succeeds(
    broker: Broker, open_router: Router, clock: FakeClock
):
    session = Session(
        "tok", "alice", open_router, broker, queue_limit=3, replay_limit=10, clock=clock
    )
    for i in range(2):  # session frame + 2 events == queue_limit
        session.deliver(event(str(i)))

    assert session.resume(last_seq=0) is True
    assert [f.seq for f in session.drain()[1:]] == [1, 2]
    assert not session.gapped


def test_resume_frame_arrives_before_the_replay(session: Session):
    session.deliver(event("un"))
    session.detach()

    session.resume(last_seq=0)

    kinds = [type(f).__name__ for f in session.drain()]
    assert kinds == ["SessionFrame", "EventFrame"]


# ── inbound frames ────────────────────────────────────────────────


def test_ping_is_answered_with_pong(session: Session):
    session.handle(Ping())

    assert isinstance(session.drain()[0], PongFrame)


def test_resume_frame_mid_stream_is_refused(session: Session):
    session.deliver(event())
    session.drain()

    session.handle(Resume(session="tok", last_seq=0))

    frames = session.drain()
    assert len(frames) == 1  # no session frame, no duplicated replay
    assert isinstance(frames[0], ErrorFrame)
    assert frames[0].code == "bad_request"


def test_resume_frame_for_another_session_is_refused(session: Session):
    session.handle(Resume(session="someone-else", last_seq=0))

    frame = session.drain()[0]
    assert isinstance(frame, ErrorFrame)
    assert frame.code == "bad_request"


def test_error_frame_in_is_sent_back(session: Session):
    error = ErrorFrame(code="bad_request", detail="bad json")

    session.handle(error)

    assert session.drain() == [error]


def test_subscribe_registers_in_the_broker(session: Session, broker: Broker):
    session.handle(Subscribe(topic_kind="conversation", topic_id="42"))

    assert broker.subscribers(CONVERSATION) == {session}
    assert session.topics() == {CONVERSATION}


def test_unsubscribe_removes_from_the_broker(session: Session, broker: Broker):
    session.handle(Subscribe(topic_kind="conversation", topic_id="42"))
    session.handle(Unsubscribe(topic_kind="conversation", topic_id="42"))

    assert session.topics() == frozenset()


def test_unknown_topic_is_refused(session: Session, broker: Broker):
    session.handle(Subscribe(topic_kind="secret", topic_id="1"))

    assert session.drain()[0].code == "unknown_topic"
    assert broker.subscribers(SECRET) == frozenset()


def test_forbidden_topic_is_refused(
    broker: Broker, open_router: Router, clock: FakeClock
):
    session = Session("tok", "mallory", open_router, broker, clock=clock)
    session.hello()
    session.drain()

    session.handle(Subscribe(topic_kind="conversation", topic_id="42"))

    assert session.drain()[0].code == "forbidden"


def test_unknown_message_type_is_refused(session: Session):
    session.handle(
        ClientMessage(type="message.explode", topic_kind="conversation", ref="r1")
    )

    error = session.drain()[0]
    assert (error.code, error.ref) == ("unknown_type", "r1")


def test_handler_error_becomes_bad_request(broker: Broker, clock: FakeClock):
    router = Router()
    router.topic("conversation")(lambda principal, topic: True)

    @router.message("message.create")
    def boom(session, frame):
        raise RuntimeError("boom")

    router.freeze()
    session = Session("tok", "alice", router, broker, clock=clock)
    session.hello()
    session.drain()

    session.handle(
        ClientMessage(type="message.create", topic_kind="conversation", ref="r1")
    )

    error = session.drain()[0]
    assert (error.code, error.ref) == ("bad_request", "r1")


def test_on_subscribe_error_does_not_break_the_subscription(
    broker: Broker, clock: FakeClock
):
    router = Router()
    router.topic("conversation")(lambda principal, topic: True)

    @router.on_subscribe("conversation")
    def boom(session, topic):
        raise RuntimeError("boom")

    router.freeze()
    session = Session("tok", "alice", router, broker, clock=clock)
    session.hello()
    session.drain()

    session.handle(Subscribe(topic_kind="conversation", topic_id="42"))

    assert session.topics() == {CONVERSATION}
    assert session.pending == 0


def test_subscribing_twice_does_not_replay_initial_state(
    broker: Broker, clock: FakeClock
):
    router = Router()
    router.topic("conversation")(lambda principal, topic: True)
    router.on_subscribe("conversation")(
        lambda session, topic: [EventFrame(type="snapshot", topic_kind=topic.kind)]
    )
    router.freeze()
    session = Session("tok", "alice", router, broker, clock=clock)
    session.hello()
    session.drain()

    session.handle(Subscribe(topic_kind="conversation", topic_id="42"))
    session.handle(Subscribe(topic_kind="conversation", topic_id="42"))

    assert len(session.drain()) == 1


# ── rate limiting ─────────────────────────────────────────────────


def test_limiter_refusal_yields_rate_limited(
    broker: Broker, open_router: Router, clock: FakeClock
):
    session = Session(
        "tok",
        "alice",
        open_router,
        broker,
        clock=clock,
        limiter=lambda principal, frame: False,
    )
    session.hello()
    session.drain()

    session.handle(Subscribe(topic_kind="conversation", topic_id="42"))

    error = session.drain()[0]
    assert error.code == "rate_limited"
    assert (error.topic_kind, error.topic_id) == ("conversation", "42")
    assert session.topics() == frozenset()


def test_limiter_echoes_the_ref(broker: Broker, open_router: Router):
    session = Session(
        "tok", "alice", open_router, broker, limiter=lambda principal, frame: False
    )
    session.hello()
    session.drain()

    session.handle(
        ClientMessage(type="message.create", topic_kind="conversation", ref="r5")
    )

    assert session.drain()[0].ref == "r5"


# ── idle clock ────────────────────────────────────────────────────


def test_idle_grows_with_time(session: Session, clock: FakeClock):
    clock.advance(30)

    assert session.idle_for() == 30


def test_client_activity_resets_idle(session: Session, clock: FakeClock):
    clock.advance(30)
    session.handle(Ping())

    assert session.idle_for() == 0


def test_delivering_does_not_reset_idle(session: Session, clock: FakeClock):
    clock.advance(30)
    session.deliver(event())

    assert session.idle_for() == 30