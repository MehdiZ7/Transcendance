"""The app's realtime features: which topics exist and what flows on them.

Imported (through `app.api.ws`, `app.api.v1.conversations` and
`app.api.v1.friends`) before the hub starts, so every registration lands
before `router.freeze()`.

| Topic | Who may subscribe | Events |
|---|---|---|
| `user:<public_id>` | that user only | `message.created`, `typing`, `friend_message.created`, `friend_typing` |
| `presence` | any logged-in user | `presence.snapshot` (on subscribe), `presence.changed` |

| Client message | Topic | Payload |
|---|---|---|
| `typing` | the sender's own `user:<public_id>` | `{"conversation_id": int, "is_typing": bool}` |
| `friend_typing` | the sender's own `user:<public_id>` | `{"friend_id": int, "is_typing": bool}` |

`typing` follows the rules of `POST /conversations/{id}/messages`: dropped
when the conversation is closed or either participant blocked the other.
`friend_typing` follows those of `POST /friends/{public_id}/messages`:
dropped unless the friendship is accepted, the sender is in it, and neither
friend blocked the other. Friendship and conversation ids overlap, hence the
separate `friend_*` names.
`presence` does not filter blocks (see the presence section below).

The wire contract is documented for the front in
`front/src/lib/realtime/README.md`.
"""

import asyncio
import logging
from collections import Counter

from sqlalchemy import and_, exists, or_, select
from sqlalchemy.orm import aliased

from app.core.db import async_session
from app.core.realtime.hub import Hub
from app.core.realtime.protocol import ClientMessage, EventFrame
from app.core.realtime.session import Session
from app.core.realtime.topics import Topic
from app.models import Conversation, Friend, User, UserBlock
from app.realtime import hub as app_hub
from app.realtime import router

__all__ = [
    "PRESENCE",
    "connection_closed",
    "connection_opened",
    "publish_to_users",
    "remember_participants",
    "user_topic",
]

logger = logging.getLogger(__name__)

PRESENCE = Topic("presence")

# Session factory for the typing checks; tests swap it for their transaction
_db = async_session


def user_topic(public_id: object) -> Topic:
    return Topic("user", str(public_id))


def publish_to_users(
    hub: Hub, type_: str, public_ids: tuple[str, ...], payload: dict
) -> None:
    """One event on each user's personal topic. Call after the DB commit."""
    for public_id in dict.fromkeys(public_ids):
        hub.publisher.publish(type_, user_topic(public_id), payload)


# ── user:<public_id> ──────────────────────────────────────────────


@router.topic("user")
def own_topic_only(principal: str, topic: Topic) -> bool:
    return topic.id == principal


# ── presence ──────────────────────────────────────────────────────

# Presence ignores blocks, on purpose for now: every logged-in user sees who
# is online, including a user they blocked or who blocked them. It only says
# online/offline, never any content. Filtering it would mean:
# - one publish per subscriber instead of one broadcast, each with a block
#   lookup, on every connect and disconnect;
# - the block and unblock routes pushing presence changes (hide or reveal),
#   and the snapshot being built per subscriber;
# - a product decision first: should a block hide presence one way or both?
# Revisit if blocking has to hide presence.

# Open sockets per user. Counted per connection, not per session: a takeover
# opens the new socket before closing the old one, so it never flickers.
_connections: Counter[str] = Counter()


@router.topic("presence")
def any_user(principal: str, topic: Topic) -> bool:
    return topic.id is None


@router.on_subscribe("presence")
def presence_snapshot(session: Session, topic: Topic) -> list[EventFrame]:
    return [
        EventFrame(
            type="presence.snapshot",
            topic_kind=topic.kind,
            payload={"online": sorted(_connections)},
        )
    ]


def connection_opened(hub: Hub, principal: str) -> None:
    _connections[principal] += 1
    if _connections[principal] == 1:
        hub.publisher.publish(
            "presence.changed", PRESENCE, {"user_id": principal, "status": "online"}
        )


def connection_closed(hub: Hub, principal: str) -> None:
    _connections[principal] -= 1
    if _connections[principal] <= 0:
        del _connections[principal]
        hub.publisher.publish(
            "presence.changed", PRESENCE, {"user_id": principal, "status": "offline"}
        )


# ── typing ────────────────────────────────────────────────────────

# conversation id -> (buyer, seller) public ids. Participants never change,
# so entries never go stale; the bound only caps memory.
_participants: dict[int, tuple[str, str]] = {}
_PARTICIPANTS_MAX = 10_000
_tasks: set[asyncio.Task[None]] = set()


def remember_participants(conversation_id: int, buyer: object, seller: object) -> None:
    if len(_participants) >= _PARTICIPANTS_MAX:
        _participants.clear()
    _participants[conversation_id] = (str(buyer), str(seller))


async def _load_participants(conversation_id: int) -> tuple[str, str] | None:
    cached = _participants.get(conversation_id)
    if cached is not None:
        return cached
    async with _db() as db:
        conversation = await db.get(Conversation, conversation_id)
        if conversation is None:
            return None
        rows = dict(
            (
                await db.execute(
                    select(User.id, User.public_id).where(
                        User.id.in_((conversation.buyer_id, conversation.seller_id))
                    )
                )
            )
            .tuples()
            .all()  # a Result has .keys(): dict() would index it
        )
    buyer, seller = rows.get(conversation.buyer_id), rows.get(conversation.seller_id)
    if buyer is None or seller is None:
        return None
    remember_participants(conversation_id, buyer, seller)
    return _participants[conversation_id]


async def _may_relay(conversation_id: int) -> bool:
    """Same rules as sending a message: open conversation, no block either way.
    Read on every relay, never cached: a block or a close can happen anytime."""
    blocked = exists().where(
        or_(
            and_(
                UserBlock.user_blocking == Conversation.buyer_id,
                UserBlock.user_blocked == Conversation.seller_id,
            ),
            and_(
                UserBlock.user_blocking == Conversation.seller_id,
                UserBlock.user_blocked == Conversation.buyer_id,
            ),
        )
    )
    async with _db() as db:
        row = (
            await db.execute(
                select(Conversation.closed, blocked.label("blocked")).where(
                    Conversation.id == conversation_id
                )
            )
        ).first()
    return row is not None and not row.closed and not row.blocked


async def _relay_typing(principal: str, conversation_id: int, is_typing: bool) -> None:
    try:
        participants = await _load_participants(conversation_id)
        # Not a member: dropped silently, like an unknown conversation
        if participants is None or principal not in participants:
            return
        if not await _may_relay(conversation_id):
            return
    except Exception:
        logger.exception("typing: loading conversation %s failed", conversation_id)
        return
    others = tuple(p for p in participants if p != principal)
    publish_to_users(
        app_hub,
        "typing",
        others,
        {
            "conversation_id": conversation_id,
            "user_id": principal,
            "is_typing": is_typing,
        },
    )


@router.message("typing")
def typing(session: Session, frame: ClientMessage) -> None:
    """Checking membership needs the DB, which a handler may not await: the
    lookup and the relay run in a task."""
    conversation_id = frame.payload.get("conversation_id")
    is_typing = frame.payload.get("is_typing")
    if isinstance(conversation_id, bool) or not isinstance(conversation_id, int):
        raise ValueError("conversation_id must be an int")
    if not isinstance(is_typing, bool):
        raise ValueError("is_typing must be a bool")
    task = asyncio.get_running_loop().create_task(
        _relay_typing(session.principal, conversation_id, is_typing)
    )
    _tasks.add(task)
    task.add_done_callback(_tasks.discard)


# friend typing


async def _other_friend(principal: str, friend_id: int) -> str | None:
    """Return the other friend's public id, or None when `principal` is not in the
    accepted friendship `friend_id`"""
    requester, address = aliased(User), aliased(User)
    blocked = exists().where(
        or_(
            and_(
                UserBlock.user_blocking == Friend.requester_id,
                UserBlock.user_blocked == Friend.address_id,
            ),
            and_(
                UserBlock.user_blocking == Friend.address_id,
                UserBlock.user_blocked == Friend.requester_id,
            ),
        )
    )
    async with _db() as db:
        row = (
            await db.execute(
                select(
                    requester.public_id.label("requester"),
                    address.public_id.label("address"),
                    blocked.label("blocked"),
                )
                .select_from(Friend)
                .join(requester, requester.id == Friend.requester_id)
                .join(address, address.id == Friend.address_id)
                .where(Friend.id == friend_id, Friend.status == "accepted")
            )
        ).first()
    if row is None or row.blocked:
        return None
    pair = (str(row.requester), str(row.address))
    if principal not in pair:
        return None
    return pair[1] if pair[0] == principal else pair[0]


async def _relay_friend_typing(principal: str, friend_id: int, is_typing: bool) -> None:
    try:
        other = await _other_friend(principal, friend_id)
    except Exception:
        logger.exception("friend_typing: loading friendship %s failed", friend_id)
        return
    if other is None:
        return
    publish_to_users(
        app_hub,
        "friend_typing",
        (other,),
        {"friend_id": friend_id, "user_id": principal, "is_typing": is_typing},
    )


@router.message("friend_typing")
def friend_typing(session: Session, frame: ClientMessage) -> None:
    """Same shape as `typing`"""
    friend_id = frame.payload.get("friend_id")
    is_typing = frame.payload.get("is_typing")
    if isinstance(friend_id, bool) or not isinstance(friend_id, int):
        raise ValueError("friend_id must be an int")
    if not isinstance(is_typing, bool):
        raise ValueError("is_typing must be a bool")
    task = asyncio.get_running_loop().create_task(
        _relay_friend_typing(session.principal, friend_id, is_typing)
    )
    _tasks.add(task)
    task.add_done_callback(_tasks.discard)
