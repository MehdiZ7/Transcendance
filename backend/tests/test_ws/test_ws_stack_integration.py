"""Full stack: socket -> transport -> registry -> session -> broker, with
business code publishing through the publisher.

Only the socket and the clock are fakes. Each client's connection runs as a
task on the test's loop; `settle` lets every task run until it blocks again,
so a test can interleave two clients and a publish deterministically.
"""

import asyncio
import json
from collections.abc import AsyncIterator, Callable

import pytest

from app.core.realtime.broker import Broker
from app.core.realtime.protocol import ClientMessage
from app.core.realtime.publisher import local_publisher
from app.core.realtime.registry import Registry
from app.core.realtime.router import Router
from app.core.realtime.session import Session
from app.core.realtime.topics import Topic
from app.core.realtime.transport import CloseCode, Connection
from conftest import FakeSocket, settle

CONVERSATION = Topic("conversation", "42")
PRESENCE = Topic("presence")

SUBSCRIBE = json.dumps(
    {"type": "subscribe", "topic_kind": "conversation", "topic_id": "42"}
)


class FakeClock:
    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds


class Client:
    """A browser: a socket, a running connection, and what it received."""

    def __init__(self, registry: Registry, principal: str) -> None:
        self.socket = FakeSocket()
        # A long tick: frames must go out on wake-up, not on a timer
        self.connection = Connection(
            self.socket, registry, principal, tick=60, handshake_timeout=1
        )
        self.task: asyncio.Task[int] | None = None

    async def connect(self, first: str = '{"type": "ping"}') -> None:
        self.socket.feed(first)
        self.task = asyncio.create_task(self.connection.run())
        await settle()

    async def send(self, raw: str) -> None:
        self.socket.feed(raw)
        await settle()

    async def drop(self) -> int:
        """The socket dies; returns the close code."""
        self.socket.hang_up()
        return await self.finish()

    async def finish(self) -> int:
        assert self.task is not None
        return await asyncio.wait_for(self.task, timeout=1)

    @property
    def session(self) -> Session:
        assert self.connection.session is not None
        return self.connection.session

    @property
    def sent(self) -> list[dict]:
        return self.socket.sent

    def types(self) -> list[str]:
        return [frame["type"] for frame in self.sent]

    def events(self) -> list[dict]:
        return [f for f in self.sent if f["type"].startswith("message.")]

    def last(self) -> dict:
        return self.sent[-1]


@pytest.fixture
def clock() -> FakeClock:
    return FakeClock()


@pytest.fixture
def app(broker: Broker):
    """The application wiring: router + publisher, as a real app would."""
    publisher = local_publisher(broker)
    router = Router()

    @router.topic("conversation")
    def may_read(principal: str, topic: Topic) -> bool:
        return topic.id == "42"

    @router.topic("presence")
    def presence_is_public(principal: str, topic: Topic) -> bool:
        return True

    @router.message("message.create")
    def create(session: Session, frame: ClientMessage) -> None:
        # business code: writes to the database, then publishes
        publisher.publish(
            "message.created",
            Topic.of(frame),
            {"text": frame.payload["text"], "by": session.principal},
        )

    router.check()
    router.freeze()
    return router, publisher


@pytest.fixture
def registry(app, broker: Broker, clock: FakeClock) -> Registry:
    router, _ = app
    return Registry(router, broker, ttl=30, clock=clock, replay_limit=4, queue_limit=3)


@pytest.fixture
def publisher(app):
    return app[1]


@pytest.fixture
async def client(registry: Registry) -> AsyncIterator[Callable[[str], Client]]:
    """Client factory; every connection still running is hung up at the end."""
    clients: list[Client] = []

    def make(principal: str) -> Client:
        clients.append(Client(registry, principal))
        return clients[-1]

    yield make

    for c in clients:
        c.socket.hang_up()
    await asyncio.gather(*(c.task for c in clients if c.task), return_exceptions=True)


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


def resume(token: str, last_seq: int) -> str:
    return json.dumps({"type": "resume", "session": token, "last_seq": last_seq})


# ── nominal ───────────────────────────────────────────────────────


async def test_two_clients_talk(client):
    alice, bob = client("alice"), client("bob")
    await alice.connect(SUBSCRIBE)
    await bob.connect(SUBSCRIBE)

    await alice.send(post("salut"))

    for c in (alice, bob):
        event = c.events()[-1]
        assert event["payload"] == {"text": "salut", "by": "alice"}
        assert event["seq"] == 1


async def test_business_code_reaches_subscribers(client, publisher):
    alice = client("alice")
    await alice.connect(SUBSCRIBE)

    publisher.publish("message.created", CONVERSATION, {"text": "hors requête"})
    await settle()

    assert alice.events()[-1]["payload"] == {"text": "hors requête"}


async def test_publishing_to_an_empty_topic_is_harmless(client, publisher):
    alice = client("alice")
    await alice.connect(SUBSCRIBE)

    assert publisher.publish("presence.join", PRESENCE) == 0

    await settle()
    assert alice.events() == []


async def test_sessions_are_independent(client, publisher):
    alice, bob = client("alice"), client("bob")
    await alice.connect(SUBSCRIBE)
    publisher.publish("message.created", CONVERSATION, {"text": "avant bob"})
    await bob.connect(SUBSCRIBE)
    publisher.publish("message.created", CONVERSATION, {"text": "après bob"})
    await settle()

    assert [e["seq"] for e in alice.events()] == [1, 2]
    assert [e["seq"] for e in bob.events()] == [1]


async def test_tokens_differ_per_connection(client, registry: Registry):
    alice, bob = client("alice"), client("bob")
    await alice.connect()
    await bob.connect()

    assert alice.session.id != bob.session.id
    assert len(registry) == 2


# ── reconnection ──────────────────────────────────────────────────


async def test_reconnect_and_resume(client, publisher):
    alice = client("alice")
    await alice.connect(SUBSCRIBE)
    publisher.publish("message.created", CONVERSATION, {"text": "avant"})
    await settle()
    token, last_seq = alice.session.id, alice.events()[-1]["seq"]

    assert await alice.drop() == CloseCode.GOING_AWAY
    publisher.publish("message.created", CONVERSATION, {"text": "pendant"})

    again = client("alice")
    await again.connect(resume(token, last_seq))

    assert again.sent[0]["resumed"] is True
    assert again.sent[0]["from_seq"] == 2
    assert again.events()[-1]["payload"]["text"] == "pendant"
    assert again.session.id == token


async def test_resume_keeps_the_subscription_alive(client, publisher):
    alice = client("alice")
    await alice.connect(SUBSCRIBE)
    token = alice.session.id
    await alice.drop()

    again = client("alice")
    await again.connect(resume(token, 0))
    publisher.publish("message.created", CONVERSATION, {"text": "après"})
    await settle()

    assert again.events()[-1]["payload"]["text"] == "après"


async def test_resume_after_the_ttl_starts_over(client, clock: FakeClock):
    alice = client("alice")
    await alice.connect(SUBSCRIBE)
    token = alice.session.id
    await alice.drop()

    clock.advance(31)

    again = client("alice")
    await again.connect(resume(token, 1))

    assert again.sent[0]["reason"] == "expired"
    assert again.session.id != token


async def test_expired_session_leaves_the_broker(
    client, registry: Registry, broker: Broker, clock: FakeClock, publisher
):
    alice = client("alice")
    await alice.connect(SUBSCRIBE)
    await alice.drop()

    clock.advance(31)
    registry.sweep()

    assert len(broker) == 0
    assert publisher.publish("message.created", CONVERSATION) == 0


async def test_another_principal_cannot_steal_a_session(client):
    alice = client("alice")
    await alice.connect(SUBSCRIBE)
    token = alice.session.id
    await alice.drop()

    mallory = client("mallory")
    await mallory.connect(resume(token, 0))

    assert mallory.sent[0]["reason"] == "expired"
    assert mallory.session.id != token


# ── back pressure ─────────────────────────────────────────────────


async def test_slow_client_is_gapped_and_asked_to_retry(client, publisher):
    slow, fast = client("alice"), client("bob")
    await slow.connect(SUBSCRIBE)
    await fast.connect(SUBSCRIBE)
    slow.socket.gate.clear()  # slow stops reading

    for i in range(10):  # queue_limit is 3
        publisher.publish("message.created", CONVERSATION, {"text": str(i)})
        await settle()
    slow.socket.gate.set()

    assert await slow.finish() == CloseCode.TRY_AGAIN_LATER
    assert slow.socket.closed_with == (CloseCode.TRY_AGAIN_LATER, "gap")
    assert len(fast.events()) == 10  # the fast one was never held back


async def test_gapped_client_reconnects_fresh(client, publisher):
    slow = client("alice")
    await slow.connect(SUBSCRIBE)
    token = slow.session.id
    slow.socket.gate.clear()
    for i in range(10):
        publisher.publish("message.created", CONVERSATION, {"text": str(i)})
        await settle()
    slow.socket.gate.set()
    await slow.finish()

    again = client("alice")
    await again.connect(resume(token, 1))

    assert again.sent[0]["reason"] == "gap"
    assert again.session.topics() == frozenset()  # must resubscribe


# ── errors ────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("raw", "code"),
    [
        pytest.param("not json", "bad_request", id="invalid-json"),
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
async def test_errors_reach_the_client_and_change_nothing(
    client, broker: Broker, raw: str, code: str
):
    alice = client("alice")
    await alice.connect()

    await alice.send(raw)

    assert alice.last()["type"] == "error"
    assert alice.last()["code"] == code
    assert len(broker) == 0


async def test_the_connection_survives_errors(client):
    alice = client("alice")
    await alice.connect("not json")

    await alice.send(SUBSCRIBE)
    await alice.send(post("salut"))

    assert alice.events()[-1]["payload"]["text"] == "salut"


async def test_unsubscribe_then_no_more_events(client, publisher):
    alice = client("alice")
    await alice.connect(SUBSCRIBE)
    await alice.send(
        json.dumps(
            {"type": "unsubscribe", "topic_kind": "conversation", "topic_id": "42"}
        )
    )

    publisher.publish("message.created", CONVERSATION, {"text": "salut"})
    await settle()

    assert alice.events() == []
