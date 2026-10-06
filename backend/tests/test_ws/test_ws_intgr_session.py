"""End-to-end tests: raw JSON in, raw JSON out.

Same stack as production minus the socket: parse_client_frame -> Session ->
Router / Broker -> Session.drain_json(). Nothing is faked except time.
"""

import json

import pytest

from app.core.realtime.broker import Broker
from app.core.realtime.protocol import (
    ClientMessage,
    EventFrame,
    parse_client_frame,
    parse_server_frame,
)
from app.core.realtime.router import Router
from app.core.realtime.session import Session
from app.core.realtime.topics import Topic


CONVERSATION = Topic("conversation", "42")


class Connection:
    """What transport.py will be: bytes in, bytes out, nothing else."""

    def __init__(self, session: Session) -> None:
        self.session = session
        self.sent: list[dict] = []

    def receive(self, raw: str) -> None:
        self.session.handle(parse_client_frame(raw))
        self.flush()

    def flush(self) -> None:
        for raw in self.session.drain_json():
            parse_server_frame(raw)  # every outgoing frame stays valid
            self.sent.append(json.loads(raw))

    def types(self) -> list[str]:
        return [frame["type"] for frame in self.sent]

    def events(self) -> list[dict]:
        return [f for f in self.sent if f["type"].startswith("message.")]


@pytest.fixture
def app_router(broker: Broker) -> Router:
    router = Router()

    @router.topic("conversation")
    def may_read(principal: str, topic: Topic) -> bool:
        return topic.id == "42"

    @router.message("message.create")
    def create(session: Session, frame: ClientMessage) -> None:
        broker.publish(
            EventFrame(
                type="message.created",
                topic_kind=frame.topic_kind,
                topic_id=frame.topic_id,
                payload={"text": frame.payload["text"], "by": session.principal},
            )
        )

    router.check()
    router.freeze()
    return router


@pytest.fixture
def alice(broker: Broker, app_router: Router) -> Connection:
    session = Session("tok-a", "alice", app_router, broker)
    session.hello()
    conn = Connection(session)
    conn.flush()
    return conn


@pytest.fixture
def bob(broker: Broker, app_router: Router) -> Connection:
    session = Session("tok-b", "bob", app_router, broker)
    session.hello()
    conn = Connection(session)
    conn.flush()
    return conn


SUBSCRIBE = json.dumps(
    {"type": "subscribe", "topic_kind": "conversation", "topic_id": "42"}
)


def post(text: str, ref: str = "r1") -> str:
    return json.dumps(
        {
            "type": "message.create",
            "topic_kind": "conversation",
            "topic_id": "42",
            "ref": ref,
            "payload": {"text": text},
        }
    )


# ── nominal flow ──────────────────────────────────────────────────


def test_handshake_comes_first(alice: Connection):
    assert alice.sent[0]["type"] == "session"
    assert alice.sent[0]["resumed"] is False


def test_two_clients_exchange_a_message(alice: Connection, bob: Connection):
    alice.receive(SUBSCRIBE)
    bob.receive(SUBSCRIBE)

    alice.receive(post("salut"))
    bob.flush()

    for conn in (alice, bob):
        event = conn.events()[-1]
        assert event["payload"] == {"text": "salut", "by": "alice"}
        assert event["seq"] == 1


def test_each_connection_has_its_own_seq(alice: Connection, bob: Connection):
    alice.receive(SUBSCRIBE)
    alice.receive(post("un"))
    bob.receive(SUBSCRIBE)  # joins later
    alice.receive(post("deux"))
    bob.flush()

    assert [e["seq"] for e in alice.events()] == [1, 2]
    assert [e["seq"] for e in bob.events()] == [1]


def test_unsubscribe_stops_the_stream(alice: Connection, bob: Connection):
    alice.receive(SUBSCRIBE)
    bob.receive(SUBSCRIBE)
    alice.receive(
        json.dumps(
            {"type": "unsubscribe", "topic_kind": "conversation", "topic_id": "42"}
        )
    )

    bob.receive(post("salut"))
    alice.flush()

    assert alice.events() == []
    assert len(bob.events()) == 1


def test_ping_pong(alice: Connection):
    alice.receive('{"type": "ping"}')

    assert alice.types()[-1] == "pong"


# ── errors ────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("raw", "code"),
    [
        pytest.param("not json", "bad_request", id="invalid-json"),
        pytest.param('{"type": "subscribe"}', "bad_request", id="missing-topic"),
        pytest.param(
            json.dumps(
                {"type": "subscribe", "topic_kind": "conversation", "topic_id": "99"}
            ),
            "forbidden",
            id="forbidden",
        ),
        pytest.param(
            json.dumps({"type": "subscribe", "topic_kind": "secret", "topic_id": "1"}),
            "unknown_topic",
            id="unknown-topic",
        ),
        pytest.param(
            json.dumps(
                {"type": "message.explode", "topic_kind": "conversation", "ref": "r1"}
            ),
            "unknown_type",
            id="unknown-type",
        ),
    ],
)
def test_errors_are_reported_and_harmless(
    alice: Connection, broker: Broker, raw: str, code: str
):
    alice.receive(raw)

    assert alice.sent[-1]["type"] == "error"
    assert alice.sent[-1]["code"] == code
    assert len(broker) == 0


def test_error_does_not_kill_the_connection(alice: Connection):
    alice.receive("not json")
    alice.receive(SUBSCRIBE)
    alice.receive(post("salut"))

    assert alice.events()[-1]["payload"]["text"] == "salut"


# ── reconnection ──────────────────────────────────────────────────


def test_resume_replays_missed_events(
    alice: Connection, bob: Connection, broker: Broker
):
    alice.receive(SUBSCRIBE)
    bob.receive(SUBSCRIBE)
    bob.receive(post("avant"))
    alice.flush()
    last_seq = alice.events()[-1]["seq"]

    alice.session.detach()  # socket lost
    bob.receive(post("pendant"))

    alice.session.resume(last_seq)
    alice.flush()

    session_frame = alice.sent[-2]
    assert (session_frame["resumed"], session_frame["from_seq"]) == (True, 2)
    assert alice.sent[-1]["payload"]["text"] == "pendant"


def test_resume_keeps_subscriptions(alice: Connection, bob: Connection):
    alice.receive(SUBSCRIBE)
    bob.receive(SUBSCRIBE)
    alice.session.detach()

    alice.session.resume(0)
    bob.receive(post("apres"))
    alice.flush()

    assert alice.events()[-1]["payload"]["text"] == "apres"


def test_gap_forces_the_client_to_start_over(
    broker: Broker, app_router: Router, bob: Connection
):
    session = Session("tok-a", "alice", app_router, broker, queue_limit=2)
    session.hello()
    alice = Connection(session)
    alice.flush()
    alice.receive(SUBSCRIBE)
    bob.receive(SUBSCRIBE)

    for i in range(5):  # alice never drains: her queue overflows
        bob.receive(post(str(i), ref=f"r{i}"))

    assert session.should_close

    session.detach()
    session.resume(1)
    alice.flush()

    frame = alice.sent[-1]
    assert (frame["type"], frame["resumed"], frame["reason"]) == (
        "session",
        False,
        "gap",
    )
    assert session.topics() == frozenset()


def test_close_frees_everything(alice: Connection, broker: Broker):
    alice.receive(SUBSCRIBE)

    alice.session.close()

    assert len(broker) == 0
    assert broker.subscribers(CONVERSATION) == frozenset()