"""Per-user quotas (app/core/quotas.py).

The limits are lowered with `quota(...)` so a test only has to seed a couple of
rows. Each test checks the refusal (409 for a total, 429 for a 24 h window),
and that what must not count does not: other users' rows, rows outside the
window, deleted rows.
"""

from datetime import UTC, datetime, timedelta

import asyncio
import pytest
import pytest_asyncio
import uuid

from sqlalchemy import delete, literal, select, text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.friends import accept_friend_request
from app.core.config import settings
from app.core.db import engine
from app.core.quotas import enforce
from app.models import Friend, User, UserBlock


OLD = datetime.now(UTC) - timedelta(hours=25)


@pytest.fixture
def quota(monkeypatch):
    def _set(name: str, value: int) -> None:
        monkeypatch.setattr(settings, f"quota_{name}", value)

    return _set


# ── listings ──────────────────────────────────────────────────────


async def test_active_listing_quota_refuses_with_409(
    client, create_user, create_listing, listing_payload, login_as, quota
):
    me = await create_user()
    login_as(me)
    quota("active_listings", 2)
    await create_listing(seller_id=me.id, status="active")
    await create_listing(seller_id=me.id, status="draft")

    response = await client.post("/api/v1/listings", json=await listing_payload())

    assert response.status_code == 409


async def test_sold_deleted_and_other_users_listings_do_not_count_as_active(
    client, create_user, create_listing, listing_payload, login_as, quota
):
    me = await create_user()
    login_as(me)
    quota("active_listings", 1)
    await create_listing(seller_id=me.id, status="sold")
    await create_listing(seller_id=me.id, status="deleted", deleted_at=datetime.now(UTC))
    await create_listing(status="active")  # someone else's

    response = await client.post("/api/v1/listings", json=await listing_payload())

    assert response.status_code == 201


async def test_listings_per_day_quota_refuses_with_429_even_for_deleted_ones(
    client, create_user, create_listing, listing_payload, login_as, quota
):
    me = await create_user()
    login_as(me)
    quota("listings_per_day", 2)
    await create_listing(seller_id=me.id, status="sold")
    # deleting does not give the slot back, or create/delete would be a loop
    await create_listing(seller_id=me.id, status="deleted", deleted_at=datetime.now(UTC))

    response = await client.post("/api/v1/listings", json=await listing_payload())

    assert response.status_code == 429


async def test_listings_older_than_a_day_do_not_count_for_the_daily_quota(
    client, create_user, create_listing, listing_payload, login_as, quota
):
    me = await create_user()
    login_as(me)
    quota("listings_per_day", 1)
    await create_listing(seller_id=me.id, status="sold", created_at=OLD)

    response = await client.post("/api/v1/listings", json=await listing_payload())

    assert response.status_code == 201


async def test_favorite_quota_refuses_new_favorites_but_not_the_existing_one(
    client, create_user, create_listing, create_listing_favorite, login_as, quota
):
    me = await create_user()
    login_as(me)
    quota("favorites", 1)
    kept = await create_listing()
    other = await create_listing()
    await create_listing_favorite(user_id=me.id, listing_id=kept.id)

    refused = await client.post(f"/api/v1/listings/{other.public_id}/favorite")
    again = await client.post(f"/api/v1/listings/{kept.public_id}/favorite")

    assert refused.status_code == 409
    assert again.status_code == 200


# ── conversations and messages ────────────────────────────────────


async def test_conversations_per_day_quota_refuses_a_new_one_with_429(
    client, create_user, create_listing, create_conversation, login_as, quota
):
    me = await create_user()
    login_as(me)
    quota("conversations_per_day", 1)
    await create_conversation(buyer_id=me.id)
    other_listing = await create_listing()

    response = await client.post(
        "/api/v1/conversations/listing", json={"listing_id": str(other_listing.public_id)}
    )

    assert response.status_code == 429


async def test_reopening_an_existing_conversation_is_not_a_new_one(
    client, create_user, create_listing, create_conversation, login_as, quota
):
    me = await create_user()
    login_as(me)
    quota("conversations_per_day", 1)
    listing = await create_listing()
    await create_conversation(listing_id=listing.id, buyer_id=me.id)

    response = await client.post(
        "/api/v1/conversations/listing", json={"listing_id": str(listing.public_id)}
    )

    assert response.status_code == 201


async def test_conversations_older_than_a_day_do_not_count(
    client, create_user, create_listing, create_conversation, login_as, quota
):
    me = await create_user()
    login_as(me)
    quota("conversations_per_day", 1)
    await create_conversation(buyer_id=me.id, created_at=OLD)
    other_listing = await create_listing()

    response = await client.post(
        "/api/v1/conversations/listing", json={"listing_id": str(other_listing.public_id)}
    )

    assert response.status_code == 201


async def test_conversation_is_full_after_the_message_quota(
    client, create_user, create_conversation, create_message, login_as, quota
):
    me = await create_user()
    login_as(me)
    quota("messages_per_conversation", 2)
    conversation = await create_conversation(buyer_id=me.id)
    await create_message(conversation_id=conversation.id, sender_id=me.id)
    await create_message(conversation_id=conversation.id, sender_id=me.id)

    response = await client.post(
        f"/api/v1/conversations/{conversation.id}/messages", json={"body": "one more"}
    )

    assert response.status_code == 409


async def test_message_quota_is_per_conversation(
    client, create_user, create_conversation, create_message, login_as, quota
):
    me = await create_user()
    login_as(me)
    quota("messages_per_conversation", 1)
    full = await create_conversation(buyer_id=me.id)
    await create_message(conversation_id=full.id, sender_id=me.id)
    empty = await create_conversation(buyer_id=me.id)

    response = await client.post(
        f"/api/v1/conversations/{empty.id}/messages", json={"body": "hello"}
    )

    assert response.status_code == 201


async def test_friend_conversation_is_full_after_the_message_quota(
    client, db_session, create_user, create_friend, login_as, quota
):
    from app.models import FriendMessage

    me = await create_user()
    login_as(me)
    other = await create_user()
    quota("messages_per_conversation", 1)
    friendship = await create_friend(requester_id=me.id, address_id=other.id, status="accepted")
    db_session.add(FriendMessage(conversation_id=friendship.id, sender_id=me.id, body="hi"))
    await db_session.flush()

    response = await client.post(
        f"/api/v1/friends/{other.public_id}/messages", json={"body": "one more"}
    )

    assert response.status_code == 409


# ── reports ───────────────────────────────────────────────────────


async def test_reports_per_day_quota_refuses_with_429(
    client, create_user, create_listing, create_report, login_as, quota
):
    me = await create_user()
    login_as(me)
    quota("reports_per_day", 1)
    await create_report(reporter_id=me.id)
    target = await create_listing()

    response = await client.post(
        "/api/v1/reports",
        json={"target_type": "listing", "target_id": str(target.public_id), "reason": "spam"},
    )

    assert response.status_code == 429


async def test_reports_older_than_a_day_do_not_count(
    client, create_user, create_listing, create_report, login_as, quota
):
    me = await create_user()
    login_as(me)
    quota("reports_per_day", 1)
    await create_report(reporter_id=me.id, created_at=OLD)
    target = await create_listing()

    response = await client.post(
        "/api/v1/reports",
        json={"target_type": "listing", "target_id": str(target.public_id), "reason": "spam"},
    )

    assert response.status_code == 201


# ── friends and blocks ────────────────────────────────────────────


async def test_pending_friend_request_quota_refuses_with_409(
    client, create_user, create_friend, login_as, quota
):
    me = await create_user()
    login_as(me)
    quota("pending_friend_requests", 1)
    await create_friend(requester_id=me.id, status="pending")
    target = await create_user()

    response = await client.post("/api/v1/friends", json={"user_id": str(target.public_id)})

    assert response.status_code == 409


async def test_received_and_answered_requests_do_not_count_as_pending_sent(
    client, create_user, create_friend, login_as, quota
):
    me = await create_user()
    login_as(me)
    quota("pending_friend_requests", 1)
    await create_friend(address_id=me.id, status="pending")  # received
    await create_friend(requester_id=me.id, status="accepted")  # answered
    target = await create_user()

    response = await client.post("/api/v1/friends", json={"user_id": str(target.public_id)})

    assert response.status_code == 201


@pytest.mark.parametrize("i_requested", [True, False])
async def test_friends_quota_counts_both_directions(
    client, create_user, create_friend, login_as, quota, i_requested
):
    me = await create_user()
    login_as(me)
    quota("friends", 1)
    if i_requested:
        await create_friend(requester_id=me.id, status="accepted")
    else:
        await create_friend(address_id=me.id, status="accepted")
    target = await create_user()

    response = await client.post("/api/v1/friends", json={"user_id": str(target.public_id)})

    assert response.status_code == 409


@pytest.mark.parametrize("full", ["me", "requester"])
async def test_accepting_a_request_is_refused_when_either_side_is_at_the_friends_quota(
    client, db_session, create_user, create_friend, login_as, quota, full
):
    me, requester = await create_user(), await create_user()
    login_as(me)
    quota("friends", 1)
    await create_friend(requester_id=(me if full == "me" else requester).id, status="accepted")
    request = await create_friend(requester_id=requester.id, address_id=me.id)

    response = await client.post(f"/api/v1/friends/{request.id}/accept")

    assert response.status_code == 409
    await db_session.refresh(request)
    assert request.status == "pending"  # kept: it can be accepted once there is room


async def test_block_quota_refuses_a_new_block_but_not_a_repeat(
    client, db_session, create_user, login_as, quota
):
    from app.models import UserBlock

    me = await create_user()
    login_as(me)
    quota("blocks", 1)
    blocked, other = await create_user(), await create_user()
    db_session.add(UserBlock(user_blocking=me.id, user_blocked=blocked.id))
    await db_session.flush()

    refused = await client.post(f"/api/v1/users/{other.public_id}/block")
    again = await client.post(f"/api/v1/users/{blocked.public_id}/block")

    assert refused.status_code == 409
    assert again.status_code == 200


# ── lock ──────────────────────────────────────────────────────


@pytest_asyncio.fixture
async def two_committed_users():
    """Two users every connection can see: the lock tests need two transactions,
    and `create_user` rows only exist inside the test's own one."""
    users = [
        User(email=f"lock-{uuid.uuid4()}@42.fr", display_name="Lock", password_hash="x")
        for _ in range(2)
    ]
    async with AsyncSession(engine, expire_on_commit=False) as session:
        session.add_all(users)
        await session.commit()
    yield users
    async with AsyncSession(engine) as session:
        await session.execute(delete(User).where(User.id.in_([u.id for u in users])))
        await session.commit()


async def test_two_users_acting_on_each_other_at_once_do_not_deadlock(two_committed_users):
    """An insert that references a user checks the foreign key with FOR KEY SHARE
    on that user's row. The quota lock must let it through, or A blocking B while
    B blocks A waits in a cycle."""
    a, b = two_committed_users
    nothing = select(literal(0))

    async def block(session, blocking, blocked):
        session.add(UserBlock(user_blocking=blocking.id, user_blocked=blocked.id))
        await session.flush()

    async with AsyncSession(engine) as t1, AsyncSession(engine) as t2:
        await enforce(t1, a.id, nothing, 1, "unused")
        await enforce(t2, b.id, nothing, 1, "unused")

        results = await asyncio.gather(block(t1, a, b), block(t2, b, a), return_exceptions=True)

        assert results == [None, None]


async def test_the_quota_lock_still_queues_a_users_own_creations(two_committed_users):
    """Two parallel creations by the same user must not both count before either
    inserts: the second enforce() waits for the first."""
    a, _ = two_committed_users
    nothing = select(literal(0))

    async with AsyncSession(engine) as first, AsyncSession(engine) as second:
        await enforce(first, a.id, nothing, 1, "unused")
        await second.execute(text("SET LOCAL lock_timeout = '200ms'"))

        with pytest.raises(DBAPIError, match="lock timeout"):
            await enforce(second, a.id, nothing, 1, "unused")


async def test_two_users_accepting_each_others_request_at_once_do_not_deadlock(
    two_committed_users,
):
    """Accepting locks both users' rows. A and B can each have a pending request
    from the other (sent at the same moment): if each side locked itself first,
    accepting both at once would wait in a cycle."""
    a, b = two_committed_users
    async with AsyncSession(engine, expire_on_commit=False) as setup:
        a_to_b = Friend(requester_id=a.id, address_id=b.id, status="pending")
        b_to_a = Friend(requester_id=b.id, address_id=a.id, status="pending")
        setup.add_all([a_to_b, b_to_a])
        await setup.commit()

    async with AsyncSession(engine) as t1, AsyncSession(engine) as t2:
        # both transactions open first, so their steps alternate below
        await t1.execute(select(literal(1)))
        await t2.execute(select(literal(1)))
        results = await asyncio.gather(
            accept_friend_request(b_to_a.id, current_user=a, session=t1),
            accept_friend_request(a_to_b.id, current_user=b, session=t2),
            return_exceptions=True,
        )

    assert not [r for r in results if isinstance(r, Exception)]
