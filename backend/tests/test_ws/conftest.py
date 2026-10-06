"""Shared test doubles.

`RecordingSink` is all a Broker needs: an object with an `id` and a
`deliver`. No socket, no asyncio, no mock library.

`FakeSocket` is all a Connection needs: an in-memory queue of client frames
and a list of what was sent. `settle` lets the connection's coroutines run
until they block again.
"""

import asyncio
import json

import pytest

from app.core.realtime.broker import Broker, Sink
from app.core.realtime.protocol import EventFrame
from app.core.realtime.router import Router
from app.core.realtime.transport import ConnectionClosed

_HANG_UP = None


async def settle(rounds: int = 20) -> None:
    """Yield to the loop until every ready coroutine has run."""
    for _ in range(rounds):
        await asyncio.sleep(0)


class FakeSocket:
    """In-memory socket. `feed` queues a client frame, `hang_up` makes the
    pending and every later receive raise ConnectionClosed. Clear `gate` to
    stall sends, like a client that stopped reading."""

    def __init__(self, *frames: str, hang_up: bool = False) -> None:
        self.inbox: asyncio.Queue[str | None] = asyncio.Queue()
        self.sent: list[dict] = []
        self.closed_with: tuple[int, str] | None = None
        self.gate = asyncio.Event()
        self.gate.set()
        for raw in frames:
            self.feed(raw)
        if hang_up:
            self.hang_up()

    def feed(self, raw: str) -> None:
        self.inbox.put_nowait(raw)

    def hang_up(self) -> None:
        self.inbox.put_nowait(_HANG_UP)

    async def receive(self) -> str:
        raw = await self.inbox.get()
        if raw is _HANG_UP:
            self.hang_up()  # stays gone
            raise ConnectionClosed("peer gone")
        return raw

    async def send(self, raw: str) -> None:
        await self.gate.wait()
        self.sent.append(json.loads(raw))

    async def close(self, code: int, reason: str = "") -> None:
        if self.closed_with is None:
            self.closed_with = (code, reason)
            self.hang_up()

    # helpers
    def types(self) -> list[str]:
        return [frame["type"] for frame in self.sent]

    def first(self, type_: str) -> dict:
        return next(frame for frame in self.sent if frame["type"] == type_)


class RecordingSink:
    """Collects what the broker delivers."""

    def __init__(self, id: str = "s1") -> None:
        self._id = id
        self.received: list[EventFrame] = []

    @property
    def id(self) -> str:
        return self._id

    def deliver(self, event: EventFrame) -> None:
        self.received.append(event)

    @property
    def types(self) -> list[str]:
        return [event.type for event in self.received]

    def __repr__(self) -> str:
        return f"<RecordingSink {self._id} n={len(self.received)}>"


class ExplodingSink(RecordingSink):
    """A broken session: deliver raises. The broker must survive it."""

    def deliver(self, event: EventFrame) -> None:
        raise RuntimeError(f"{self.id} is broken")


class SelfRemovingSink(RecordingSink):
    """Unsubscribes itself from inside deliver, the classic
    mutation-during-iteration trap."""

    def __init__(self, id: str, broker: Broker) -> None:
        super().__init__(id)
        self._broker = broker

    def deliver(self, event: EventFrame) -> None:
        super().deliver(event)
        from app.core.realtime.topics import Topic

        self._broker.unsubscribe(Topic.of(event), self)


@pytest.fixture
def broker() -> Broker:
    return Broker()


@pytest.fixture
def router() -> Router:
    return Router()


@pytest.fixture
def sink() -> RecordingSink:
    return RecordingSink("s1")


@pytest.fixture
def other_sink() -> RecordingSink:
    return RecordingSink("s2")


def test_recording_sink_satisfies_the_protocol():
    assert isinstance(RecordingSink(), Sink)