"""The app's realtime features (app/realtime_topics.py): authorizers,
presence, the typing relay, and message.created published by the REST route."""

import asyncio
import uuid
from contextlib import asynccontextmanager

import pytest

from app import realtime_topics
from app.core.realtime.hub import Hub
from app.core.realtime.protocol import ClientMessage
from app.core.realtime.router import Router
from app.core.realtime.topics import Topic
from app.main import app
from app.models import UserBlock
from app.realtime import get_hub
from app.realtime_topics import (
    PRESENCE,
    any_user,
    connection_closed,
    connection_opened,
    friend_typing,
    own_topic_only,
    presence_snapshot,
    remember_participants,
    typing,
    user_topic,
)

ALICE = str(uuid.uuid4())
BOB = str(uuid.uuid4())
EVE = str(uuid.uuid4())


@pytest.fixture
def hub() -> Hub:
    return Hub(Router(), sweep_every=60)


@pytest.fixture(autouse=True)
def clean_state(monkeypatch):
    monkeypatch.setattr(realtime_topics, "_connections", realtime_topics.Counter())
    monkeypatch.setattr(realtime_topics, "_participants", {})


class RecordingSink:
    def __init__(self, id: str) -> None:
        self.id = id
        self.received = []

    def deliver(self, event) -> None:
        self.received.append(event)


def listen(hub: Hub, topic: Topic, name: str = "s1") -> RecordingSink:
    sink = RecordingSink(name)
    hub.broker.subscribe(topic, sink)
    return sink


def test_user_topic_is_private():
    assert own_topic_only(ALICE, user_topic(ALICE))
    assert not own_topic_only(ALICE, user_topic(BOB))


def test_presence_is_global_only():
    assert any_user(ALICE, PRESENCE)
    assert not any_user(ALICE, Topic("presence", "x"))


def test_presence_announces_first_open_and_last_close_only(hub):
    sink = listen(hub, PRESENCE)

    connection_opened(hub, ALICE)
    connection_opened(hub, ALICE)  # second tab
    connection_closed(hub, ALICE)
    connection_closed(hub, ALICE)

    assert [e.payload for e in sink.received] == [
        {"user_id": ALICE, "status": "online"},
        {"user_id": ALICE, "status": "offline"},
    ]


def test_presence_snapshot_lists_connected_users(hub):
    connection_opened(hub, BOB)
    connection_opened(hub, ALICE)

    [event] = presence_snapshot(None, PRESENCE)

    assert event.type == "presence.snapshot"
    assert event.payload == {"online": sorted([ALICE, BOB])}


def _typing_frame(**payload) -> ClientMessage:
    return ClientMessage(
        type="typing", topic_kind="user", topic_id=ALICE, payload=payload
    )


@pytest.mark.parametrize(
    "payload",
    [
        {},
        {"conversation_id": "1", "is_typing": True},
        {"conversation_id": 1, "is_typing": 1},
        {"conversation_id": True, "is_typing": True},
    ],
)
def test_typing_rejects_malformed_payload(payload):
    session = type("S", (), {"principal": ALICE})()
    with pytest.raises(ValueError):
        typing(session, _typing_frame(**payload))


async def _run_typing(
    principal: str, conversation_id: int, is_typing: bool = True
) -> None:
    session = type("S", (), {"principal": principal})()
    typing(session, _typing_frame(conversation_id=conversation_id, is_typing=is_typing))
    await asyncio.gather(*realtime_topics._tasks)


@pytest.fixture
def typing_db(db_session, monkeypatch, hub):
    """The relay reads the test transaction and publishes on the test hub."""

    @asynccontextmanager
    async def _db():
        yield db_session

    monkeypatch.setattr(realtime_topics, "_db", _db)
    monkeypatch.setattr(realtime_topics, "app_hub", hub)
    return db_session


@pytest.fixture
def pair(create_user, create_conversation):
    """(buyer, seller, conversation)"""

    async def _create(**kwargs):
        buyer, seller = await create_user(), await create_user()
        conversation = await create_conversation(
            buyer_id=buyer.id, seller_id=seller.id, **kwargs
        )
        return buyer, seller, conversation

    return _create


async def test_typing_is_relayed_to_the_other_participant_only(hub, typing_db, pair):
    buyer, seller, conversation = await pair()
    to_buyer = listen(hub, user_topic(buyer.public_id), "b")
    to_seller = listen(hub, user_topic(seller.public_id), "s")

    await _run_typing(str(buyer.public_id), conversation.id)

    assert to_buyer.received == []
    assert [(e.type, e.payload) for e in to_seller.received] == [
        (
            "typing",
            {
                "conversation_id": conversation.id,
                "user_id": str(buyer.public_id),
                "is_typing": True,
            },
        )
    ]


async def test_typing_from_a_non_member_is_dropped_on_a_cold_cache(
    hub, typing_db, pair, create_user
):
    buyer, seller, conversation = await pair()
    eve = await create_user()
    to_buyer = listen(hub, user_topic(buyer.public_id), "b")
    to_seller = listen(hub, user_topic(seller.public_id), "s")

    await _run_typing(str(eve.public_id), conversation.id)

    assert to_buyer.received == [] and to_seller.received == []


async def test_typing_in_a_closed_conversation_is_dropped(hub, typing_db, pair):
    buyer, seller, conversation = await pair(closed=True)
    to_seller = listen(hub, user_topic(seller.public_id), "s")

    await _run_typing(str(buyer.public_id), conversation.id)

    assert to_seller.received == []


@pytest.mark.parametrize("buyer_blocks", [True, False])
async def test_typing_is_dropped_when_either_side_blocked(
    hub, typing_db, pair, buyer_blocks
):
    buyer, seller, conversation = await pair()
    blocking, blocked = (buyer, seller) if buyer_blocks else (seller, buyer)
    typing_db.add(UserBlock(user_blocking=blocking.id, user_blocked=blocked.id))
    await typing_db.flush()
    to_seller = listen(hub, user_topic(seller.public_id), "s")

    await _run_typing(str(buyer.public_id), conversation.id)

    assert to_seller.received == []


async def test_typing_from_a_non_member_is_dropped(hub, monkeypatch):
    monkeypatch.setattr(realtime_topics, "app_hub", hub)
    remember_participants(7, ALICE, BOB)
    alice, bob = listen(hub, user_topic(ALICE), "a"), listen(hub, user_topic(BOB), "b")

    await _run_typing(EVE, 7)

    assert alice.received == [] and bob.received == []


async def test_send_message_publishes_to_both_participants(
    client, create_conversation, create_user, login_as, hub
):
    buyer, seller = await create_user(), await create_user()
    conversation = await create_conversation(buyer_id=buyer.id, seller_id=seller.id)
    to_buyer = listen(hub, user_topic(buyer.public_id), "b")
    to_seller = listen(hub, user_topic(seller.public_id), "s")
    app.dependency_overrides[get_hub] = lambda: hub
    login_as(buyer)

    response = await client.post(
        f"/api/v1/conversations/{conversation.id}/messages", json={"body": "dispo ?"}
    )

    assert response.status_code == 201
    for sink in (to_buyer, to_seller):
        [event] = sink.received
        assert event.type == "message.created"
        assert event.payload == response.json()
    # the typing relay can now skip the DB for this conversation
    assert realtime_topics._participants[conversation.id] == (
        str(buyer.public_id),
        str(seller.public_id),
    )


# friend typing


def _friend_typing_frame(**payload) -> ClientMessage:
    return ClientMessage(
        type="friend_typing", topic_kind="user", topic_id=ALICE, payload=payload
    )


@pytest.mark.parametrize(
    "payload",
    [
        {},
        {"friend_id": "1", "is_typing": True},
        {"friend_id": 1, "is_typing": 1},
        {"friend_id": True, "is_typing": True},
    ],
)
def test_friend_typing_rejects_malformed_payload(payload):
    session = type("S", (), {"principal": ALICE})()
    with pytest.raises(ValueError):
        friend_typing(session, _friend_typing_frame(**payload))


async def _run_friend_typing(
    principal: str, friend_id: int, is_typing: bool = True
) -> None:
    session = type("S", (), {"principal": principal})()
    friend_typing(
        session, _friend_typing_frame(friend_id=friend_id, is_typing=is_typing)
    )
    await asyncio.gather(*realtime_topics._tasks)


@pytest.fixture
def friends(create_user, create_friend):
    """(requester, address, friendship)"""

    async def _create(status: str = "accepted"):
        requester, address = await create_user(), await create_user()
        friendship = await create_friend(
            requester_id=requester.id, address_id=address.id, status=status
        )
        return requester, address, friendship

    return _create


@pytest.mark.parametrize("from_requester", [True, False])
async def test_friend_typing_is_relayed_to_the_other_friend_only(
    hub, typing_db, friends, from_requester
):
    requester, address, friendship = await friends()
    sender, other = (requester, address) if from_requester else (address, requester)
    to_sender = listen(hub, user_topic(sender.public_id), "s")
    to_other = listen(hub, user_topic(other.public_id), "o")

    await _run_friend_typing(str(sender.public_id), friendship.id)

    assert to_sender.received == []
    assert [(e.type, e.payload) for e in to_other.received] == [
        (
            "friend_typing",
            {
                "friend_id": friendship.id,
                "user_id": str(sender.public_id),
                "is_typing": True,
            },
        )
    ]


async def test_friend_typing_from_a_non_member_is_dropped(
    hub, typing_db, friends, create_user
):
    requester, address, friendship = await friends()
    eve = await create_user()
    to_requester = listen(hub, user_topic(requester.public_id), "r")
    to_address = listen(hub, user_topic(address.public_id), "a")

    await _run_friend_typing(str(eve.public_id), friendship.id)

    assert to_requester.received == [] and to_address.received == []


async def test_friend_typing_on_a_pending_request_is_dropped(hub, typing_db, friends):
    requester, address, friendship = await friends(status="pending")
    to_address = listen(hub, user_topic(address.public_id), "a")

    await _run_friend_typing(str(requester.public_id), friendship.id)

    assert to_address.received == []


async def test_friend_typing_on_an_unknown_friendship_is_dropped(hub, typing_db):
    alice = listen(hub, user_topic(ALICE), "a")

    await _run_friend_typing(ALICE, 0)

    assert alice.received == []


@pytest.mark.parametrize("requester_blocks", [True, False])
async def test_friend_typing_is_dropped_when_either_side_blocked(
    hub, typing_db, friends, requester_blocks
):
    # Blocking deletes the friendship, so the row is gone and the relay drops
    # it anyway; the block check covers a block and a friendship coexisting.
    requester, address, friendship = await friends()
    blocking, blocked = (
        (requester, address) if requester_blocks else (address, requester)
    )
    typing_db.add(UserBlock(user_blocking=blocking.id, user_blocked=blocked.id))
    await typing_db.flush()
    to_address = listen(hub, user_topic(address.public_id), "a")

    await _run_friend_typing(str(requester.public_id), friendship.id)

    assert to_address.received == []


async def test_send_friend_message_publishes_to_both_friends(
    client, create_user, create_friend, login_as, hub
):
    me, other = await create_user(), await create_user()
    await create_friend(requester_id=me.id, address_id=other.id, status="accepted")
    to_me = listen(hub, user_topic(me.public_id), "m")
    to_other = listen(hub, user_topic(other.public_id), "o")
    app.dependency_overrides[get_hub] = lambda: hub
    login_as(me)

    response = await client.post(
        f"/api/v1/friends/{other.public_id}/messages", json={"body": "Salut"}
    )

    assert response.status_code == 201
    for sink in (to_me, to_other):
        [event] = sink.received
        assert event.type == "friend_message.created"
        assert event.payload == response.json()


async def test_refused_friend_message_publishes_nothing(
    client, create_user, create_friend, login_as, hub, db_session
):
    me, other = await create_user(), await create_user()
    await create_friend(requester_id=me.id, address_id=other.id, status="accepted")
    db_session.add(UserBlock(user_blocking=other.id, user_blocked=me.id))
    await db_session.flush()
    to_other = listen(hub, user_topic(other.public_id), "o")
    app.dependency_overrides[get_hub] = lambda: hub
    login_as(me)

    response = await client.post(
        f"/api/v1/friends/{other.public_id}/messages", json={"body": "Salut"}
    )

    assert response.status_code == 403
    assert to_other.received == []
