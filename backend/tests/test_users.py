from datetime import UTC, datetime

import pytest
from sqlalchemy import select

from app.models import Friend, FriendMessage, UserBlock


async def test_get_me_is_empty_when_anonymous(client):
    response = await client.get("/api/v1/users/me")

    assert response.status_code == 204


async def test_get_me_returns_current_user(client, create_user, login_as):
    me = await create_user(display_name="Jean Dupont", email="jean@student.42.fr")
    login_as(me)

    response = await client.get("/api/v1/users/me")

    assert response.status_code == 200
    body = response.json()
    assert body["display_name"] == "Jean Dupont"
    assert body["email"] == "jean@student.42.fr"
    assert body["friends_count"] == 0
    assert body["listings_count"] == 0
    assert body["reviews_count"] == 0


async def test_get_me_counts_related_rows(client, create_listing, create_review, create_user, login_as):
    me = await create_user()
    login_as(me)
    await create_listing(seller_id=me.id)
    reviewer = await create_user()
    await create_review(subject_id=me.id, author_id=reviewer.id)

    response = await client.get("/api/v1/users/me")

    body = response.json()
    assert body["listings_count"] == 1
    assert body["reviews_count"] == 1


async def test_patch_me_requires_authentication(client):
    response = await client.patch("/api/v1/users/me", json={"display_name": "Nope"})

    assert response.status_code == 401


async def test_patch_me_updates_display_name_and_bio(client, create_user, login_as):
    me = await create_user()
    login_as(me)
    original_updated_at = me.updated_at

    response = await client.patch(
        "/api/v1/users/me", json={"display_name": "Nouveau nom", "bio": "Nouvelle bio"}
    )

    assert response.status_code == 200
    body = response.json()
    assert body["display_name"] == "Nouveau nom"
    assert body["bio"] == "Nouvelle bio"
    assert body["updated_at"] != original_updated_at.isoformat()

    follow_up = await client.get("/api/v1/users/me")
    assert follow_up.json()["display_name"] == "Nouveau nom"


async def test_patch_me_ignores_unset_fields(client, create_user, login_as):
    me = await create_user(bio="Bio existante")
    login_as(me)

    response = await client.patch("/api/v1/users/me", json={"display_name": "Juste le nom"})

    assert response.json()["bio"] == "Bio existante"


async def test_patch_me_sets_location_id(client, create_user, create_location, login_as):
    login_as(await create_user())
    location = await create_location()

    response = await client.patch("/api/v1/users/me", json={"location_id": location.id})

    assert response.status_code == 200
    assert response.json()["location_id"] == location.id

    follow_up = await client.get("/api/v1/users/me")
    assert follow_up.json()["location_id"] == location.id


async def test_patch_me_returns_404_for_unknown_location(client, create_user, login_as):
    login_as(await create_user())

    response = await client.patch("/api/v1/users/me", json={"location_id": 999999})

    assert response.status_code == 404


async def test_get_user_returns_public_profile(client, create_user):
    user = await create_user(display_name="Camille R.", bio="42 Paris student")

    response = await client.get(f"/api/v1/users/{user.public_id}")

    assert response.status_code == 200
    body = response.json()
    assert body["display_name"] == "Camille R."
    assert body["bio"] == "42 Paris student"
    assert body["role"] == "user"
    assert "email" not in body


async def test_get_user_computes_rating_average(client, create_user):
    user = await create_user(rating=45, rating_count=10)

    response = await client.get(f"/api/v1/users/{user.public_id}")

    assert response.json()["rating"] == 4.5


async def test_get_user_says_when_that_user_has_blocked_me(
    client, db_session, create_user, login_as
):
    me = await create_user()
    login_as(me)
    other = await create_user()
    db_session.add(UserBlock(user_blocking=other.id, user_blocked=me.id))
    await db_session.flush()

    response = await client.get(f"/api/v1/users/{other.public_id}")

    assert response.json()["has_blocked_me"] is True


async def test_get_user_does_not_reveal_a_block_i_placed_myself_as_has_blocked_me(
    client, db_session, create_user, login_as
):
    me = await create_user()
    login_as(me)
    other = await create_user()
    db_session.add(UserBlock(user_blocking=me.id, user_blocked=other.id))
    await db_session.flush()

    response = await client.get(f"/api/v1/users/{other.public_id}")

    assert response.json()["has_blocked_me"] is False


async def test_get_user_has_blocked_me_ignores_blocks_between_other_people(
    client, db_session, create_user, login_as
):
    login_as(await create_user())
    a, b = await create_user(), await create_user()
    db_session.add(UserBlock(user_blocking=a.id, user_blocked=b.id))
    await db_session.flush()

    response = await client.get(f"/api/v1/users/{a.public_id}")

    assert response.json()["has_blocked_me"] is False


async def test_get_user_has_blocked_me_is_false_without_a_session(
    client, db_session, create_user
):
    other, someone = await create_user(), await create_user()
    db_session.add(UserBlock(user_blocking=other.id, user_blocked=someone.id))
    await db_session.flush()

    response = await client.get(f"/api/v1/users/{other.public_id}")

    assert response.status_code == 200
    assert response.json()["has_blocked_me"] is False


async def test_get_user_has_blocked_me_is_false_on_my_own_profile(client, create_user, login_as):
    me = await create_user()
    login_as(me)

    response = await client.get(f"/api/v1/users/{me.public_id}")

    assert response.json()["has_blocked_me"] is False


async def test_get_user_returns_404_for_unknown_public_id(client):
    response = await client.get("/api/v1/users/00000000-0000-0000-0000-000000000000")

    assert response.status_code == 404


async def test_list_user_reviews_returns_reviews_with_author(client, create_user, create_review):
    subject = await create_user(display_name="Seller")
    author = await create_user(display_name="Reviewer")
    await create_review(subject_id=subject.id, author_id=author.id, rating=5, body="Great seller")

    response = await client.get(f"/api/v1/users/{subject.public_id}/reviews")

    assert response.status_code == 200
    body = response.json()
    assert len(body) == 1
    assert body[0]["rating"] == 5
    assert body[0]["body"] == "Great seller"
    assert body[0]["author"]["display_name"] == "Reviewer"


async def test_list_user_reviews_excludes_deleted(client, create_user, create_review):
    subject = await create_user()
    await create_review(subject_id=subject.id, rating=1, deleted_at=datetime.now(UTC))

    response = await client.get(f"/api/v1/users/{subject.public_id}/reviews")

    assert response.json() == []


async def test_list_user_reviews_returns_404_for_unknown_user(client):
    response = await client.get("/api/v1/users/00000000-0000-0000-0000-000000000000/reviews")

    assert response.status_code == 404


async def test_block_user_requires_authentication(client, create_user):
    target = await create_user()

    response = await client.post(f"/api/v1/users/{target.public_id}/block")

    assert response.status_code == 401


async def test_block_user_creates_block_row(client, db_session, create_user, login_as):
    me = await create_user()
    login_as(me)
    target = await create_user()

    response = await client.post(f"/api/v1/users/{target.public_id}/block")

    assert response.status_code == 200
    assert response.json() == {"message": "User blocked"}

    block = await db_session.scalar(
        select(UserBlock).where(
            UserBlock.user_blocking == me.id, UserBlock.user_blocked == target.id
        )
    )
    assert block is not None


async def test_block_user_is_idempotent(client, create_user, login_as):
    login_as(await create_user())
    target = await create_user()

    first = await client.post(f"/api/v1/users/{target.public_id}/block")
    second = await client.post(f"/api/v1/users/{target.public_id}/block")

    assert first.status_code == 200
    assert second.status_code == 200


async def test_block_user_returns_400_for_self(client, create_user, login_as):
    me = await create_user()
    login_as(me)

    response = await client.post(f"/api/v1/users/{me.public_id}/block")

    assert response.status_code == 400


async def test_block_user_returns_404_for_unknown_user(client, create_user, login_as):
    login_as(await create_user())

    response = await client.post("/api/v1/users/00000000-0000-0000-0000-000000000000/block")

    assert response.status_code == 404


@pytest.mark.parametrize(
    ("i_requested", "status"),
    [(True, "accepted"), (False, "accepted"), (True, "pending"), (False, "pending")],
)
async def test_block_user_deletes_the_friendship_whoever_asked(
    client, db_session, create_user, create_friend, login_as, i_requested, status
):
    me = await create_user()
    login_as(me)
    target = await create_user()
    pair = (
        {"requester_id": me.id, "address_id": target.id}
        if i_requested
        else {"requester_id": target.id, "address_id": me.id}
    )
    friendship = await create_friend(status=status, **pair)

    response = await client.post(f"/api/v1/users/{target.public_id}/block")

    assert response.status_code == 200
    assert await db_session.scalar(select(Friend).where(Friend.id == friendship.id)) is None


async def test_block_user_leaves_other_friendships_alone(
    client, db_session, create_user, create_friend, login_as
):
    me = await create_user()
    login_as(me)
    target, third = await create_user(), await create_user()
    mine = await create_friend(requester_id=me.id, address_id=third.id, status="accepted")
    theirs = await create_friend(requester_id=target.id, address_id=third.id, status="accepted")

    await client.post(f"/api/v1/users/{target.public_id}/block")

    remaining = set(await db_session.scalars(select(Friend.id).where(Friend.id.in_((mine.id, theirs.id)))))
    assert remaining == {mine.id, theirs.id}


async def test_block_user_deletes_the_direct_messages_with_the_friendship(
    client, db_session, create_user, create_friend, login_as
):
    # friend_messages hang off the friends row (ON DELETE CASCADE): the
    # history goes with the friendship, as with DELETE /friends/{public_id}
    me = await create_user()
    login_as(me)
    target = await create_user()
    friendship = await create_friend(requester_id=me.id, address_id=target.id, status="accepted")
    db_session.add(FriendMessage(conversation_id=friendship.id, sender_id=me.id, body="salut"))
    await db_session.flush()

    await client.post(f"/api/v1/users/{target.public_id}/block")

    messages = await db_session.scalars(
        select(FriendMessage).where(FriendMessage.conversation_id == friendship.id)
    )
    assert messages.all() == []


async def test_a_friend_request_can_be_sent_again_after_a_block_is_lifted(
    client, create_user, create_friend, login_as
):
    me = await create_user()
    login_as(me)
    target = await create_user()
    await create_friend(requester_id=me.id, address_id=target.id, status="accepted")

    await client.post(f"/api/v1/users/{target.public_id}/block")
    await client.delete(f"/api/v1/users/{target.public_id}/block")
    response = await client.post("/api/v1/friends", json={"user_id": str(target.public_id)})

    assert response.status_code == 201


async def test_block_user_does_not_create_a_friend_row_when_none_existed(
    client, db_session, create_user, login_as
):
    login_as(await create_user())
    target = await create_user()

    response = await client.post(f"/api/v1/users/{target.public_id}/block")

    assert response.status_code == 200
    friendship = await db_session.scalar(select(Friend).where(Friend.address_id == target.id))
    assert friendship is None


async def test_block_user_closes_every_conversation_between_the_two(
    client, db_session, create_user, create_listing, create_conversation, login_as
):
    me = await create_user()
    login_as(me)
    other = await create_user()
    # one where I'm the buyer, one where I'm the seller
    my_listing = await create_listing(seller_id=me.id)
    conv_as_seller = await create_conversation(listing_id=my_listing.id, buyer_id=other.id)
    other_listing = await create_listing(seller_id=other.id)
    conv_as_buyer = await create_conversation(listing_id=other_listing.id, buyer_id=me.id)

    response = await client.post(f"/api/v1/users/{other.public_id}/block")

    assert response.status_code == 200
    await db_session.refresh(conv_as_seller)
    await db_session.refresh(conv_as_buyer)
    assert conv_as_seller.closed is True
    assert conv_as_buyer.closed is True


async def test_block_user_does_not_touch_a_conversation_already_closed(
    client, db_session, create_user, create_listing, create_conversation, login_as
):
    me = await create_user()
    login_as(me)
    other = await create_user()
    listing = await create_listing(seller_id=me.id)
    conversation = await create_conversation(listing_id=listing.id, buyer_id=other.id, closed=True)

    response = await client.post(f"/api/v1/users/{other.public_id}/block")

    assert response.status_code == 200
    await db_session.refresh(conversation)
    assert conversation.closed is True


async def test_unblock_user_requires_authentication(client, create_user):
    target = await create_user()

    response = await client.delete(f"/api/v1/users/{target.public_id}/block")

    assert response.status_code == 401


async def test_unblock_user_removes_the_block_row(client, db_session, create_user, login_as):
    me = await create_user()
    login_as(me)
    target = await create_user()
    db_session.add(UserBlock(user_blocking=me.id, user_blocked=target.id))
    await db_session.flush()

    response = await client.delete(f"/api/v1/users/{target.public_id}/block")

    assert response.status_code == 200
    remaining = await db_session.scalar(
        select(UserBlock).where(
            UserBlock.user_blocking == me.id, UserBlock.user_blocked == target.id
        )
    )
    assert remaining is None


async def test_unblock_user_is_idempotent_when_not_blocked(client, create_user, login_as):
    login_as(await create_user())
    target = await create_user()

    response = await client.delete(f"/api/v1/users/{target.public_id}/block")

    assert response.status_code == 200


async def test_unblock_user_reopens_conversations_the_block_closed(
    client, db_session, create_user, create_listing, create_conversation, login_as
):
    me = await create_user()
    login_as(me)
    other = await create_user()
    my_listing = await create_listing(seller_id=me.id)
    conv_as_seller = await create_conversation(listing_id=my_listing.id, buyer_id=other.id)
    other_listing = await create_listing(seller_id=other.id)
    conv_as_buyer = await create_conversation(listing_id=other_listing.id, buyer_id=me.id)
    db_session.add(UserBlock(user_blocking=me.id, user_blocked=other.id))
    await db_session.flush()
    for conv in (conv_as_seller, conv_as_buyer):
        conv.closed = True
    await db_session.flush()

    response = await client.delete(f"/api/v1/users/{other.public_id}/block")

    assert response.status_code == 200
    await db_session.refresh(conv_as_seller)
    await db_session.refresh(conv_as_buyer)
    assert conv_as_seller.closed is False
    assert conv_as_buyer.closed is False


async def test_unblock_user_reopening_ignores_conversations_with_third_parties(
    client, db_session, create_user, create_listing, create_conversation, login_as
):
    me = await create_user()
    login_as(me)
    other, third = await create_user(), await create_user()
    listing = await create_listing(seller_id=me.id)
    conv_with_third = await create_conversation(listing_id=listing.id, buyer_id=third.id, closed=True)
    db_session.add(UserBlock(user_blocking=me.id, user_blocked=other.id))
    await db_session.flush()

    await client.delete(f"/api/v1/users/{other.public_id}/block")

    await db_session.refresh(conv_with_third)
    assert conv_with_third.closed is True


async def test_unblock_user_without_an_active_block_does_not_reopen_anything(
    client, db_session, create_user, create_listing, create_conversation, login_as
):
    """Idempotent unblock (no UserBlock row) must not touch conversations that
    are closed for some unrelated reason."""
    me = await create_user()
    login_as(me)
    other = await create_user()
    listing = await create_listing(seller_id=me.id)
    conversation = await create_conversation(listing_id=listing.id, buyer_id=other.id, closed=True)

    response = await client.delete(f"/api/v1/users/{other.public_id}/block")

    assert response.status_code == 200
    await db_session.refresh(conversation)
    assert conversation.closed is True


async def test_list_blocked_users_requires_authentication(client):
    response = await client.get("/api/v1/users/me/blocks")

    assert response.status_code == 401


async def test_list_blocked_users_returns_only_users_i_blocked(
    client, db_session, create_user, login_as
):
    me = await create_user()
    login_as(me)
    blocked = await create_user(display_name="Blocked One")
    other = await create_user()
    db_session.add(UserBlock(user_blocking=me.id, user_blocked=blocked.id))
    db_session.add(UserBlock(user_blocking=other.id, user_blocked=me.id))  # blocked me, not mine
    await db_session.flush()

    response = await client.get("/api/v1/users/me/blocks")

    assert response.status_code == 200
    body = response.json()
    assert len(body) == 1
    assert body[0]["display_name"] == "Blocked One"


async def test_list_user_friends_requires_authentication(client, create_user):
    user = await create_user()

    response = await client.get(f"/api/v1/users/{user.public_id}/friends")

    assert response.status_code == 401


async def test_list_user_friends_returns_accepted_friends_only(
    client, create_user, create_friend, login_as
):
    login_as(await create_user())
    user = await create_user()
    accepted_friend = await create_user(display_name="Accepted Friend")
    pending_friend = await create_user(display_name="Pending Friend")
    await create_friend(requester_id=user.id, address_id=accepted_friend.id, status="accepted")
    await create_friend(requester_id=user.id, address_id=pending_friend.id, status="pending")

    response = await client.get(f"/api/v1/users/{user.public_id}/friends")

    assert response.status_code == 200
    names = [friend["display_name"] for friend in response.json()]
    assert names == ["Accepted Friend"]


async def test_list_user_friends_returns_404_for_unknown_user(client, create_user, login_as):
    login_as(await create_user())

    response = await client.get("/api/v1/users/00000000-0000-0000-0000-000000000000/friends")

    assert response.status_code == 404


async def test_list_user_listings_returns_only_that_sellers_active_and_sold_listings(
    client, create_user, create_listing
):
    seller = await create_user()
    other = await create_user()
    await create_listing(title="For sale", seller_id=seller.id, status="active")
    await create_listing(title="Sold", seller_id=seller.id, status="sold")
    await create_listing(title="Draft", seller_id=seller.id, status="draft")
    await create_listing(title="Archived", seller_id=seller.id, status="archived")
    await create_listing(title="Not mine", seller_id=other.id, status="active")

    response = await client.get(f"/api/v1/users/{seller.public_id}/listings")

    assert response.status_code == 200
    body = response.json()
    assert {item["title"] for item in body["data"]} == {"For sale", "Sold"}
    assert body["total"] == 2


async def test_list_user_listings_does_not_require_authentication(client, create_user, create_listing):
    seller = await create_user()
    await create_listing(seller_id=seller.id)

    response = await client.get(f"/api/v1/users/{seller.public_id}/listings")

    assert response.status_code == 200


async def test_list_user_listings_returns_404_for_unknown_user(client):
    response = await client.get("/api/v1/users/00000000-0000-0000-0000-000000000000/listings")

    assert response.status_code == 404


async def test_list_user_favorites_does_not_require_authentication(client, create_user):
    user = await create_user()

    response = await client.get(f"/api/v1/users/{user.public_id}/favorites")

    assert response.status_code == 200


async def test_list_user_favorites_returns_404_for_unknown_user(client):
    response = await client.get("/api/v1/users/00000000-0000-0000-0000-000000000000/favorites")

    assert response.status_code == 404


async def test_list_user_favorites_returns_only_that_users_favorited_listings(
    client, create_user, create_listing, create_listing_favorite
):
    owner = await create_user()
    favorited = await create_listing(title="Favorited by owner")
    await create_listing_favorite(listing_id=favorited.id, user_id=owner.id)
    await create_listing(title="Not favorited")
    other_favorited = await create_listing(title="Favorited by someone else")
    await create_listing_favorite(listing_id=other_favorited.id, user_id=(await create_user()).id)

    response = await client.get(f"/api/v1/users/{owner.public_id}/favorites")

    assert response.status_code == 200
    body = response.json()
    assert [item["title"] for item in body["data"]] == ["Favorited by owner"]
    assert body["total"] == 1


async def test_list_user_favorites_is_favorited_reflects_the_viewer_not_the_owner(
    client, create_user, create_listing, create_listing_favorite, login_as
):
    owner = await create_user()
    viewer = await create_user()
    login_as(viewer)
    listing = await create_listing(title="Favorited by owner only")
    await create_listing_favorite(listing_id=listing.id, user_id=owner.id)

    response = await client.get(f"/api/v1/users/{owner.public_id}/favorites")

    assert response.json()["data"][0]["is_favorited"] is False


async def test_list_user_favorites_orders_most_recently_favorited_first(
    client, create_user, create_listing, create_listing_favorite
):
    # now() is transaction-start time in Postgres, not statement time - both
    # inserts would otherwise land on the exact same created_at inside the
    # single transaction a test runs in, making the order unstable.
    owner = await create_user()
    first = await create_listing(title="Favorited first")
    second = await create_listing(title="Favorited second")
    await create_listing_favorite(
        listing_id=first.id, user_id=owner.id, created_at=datetime(2026, 1, 1, tzinfo=UTC)
    )
    await create_listing_favorite(
        listing_id=second.id, user_id=owner.id, created_at=datetime(2026, 1, 2, tzinfo=UTC)
    )

    response = await client.get(f"/api/v1/users/{owner.public_id}/favorites")

    titles = [item["title"] for item in response.json()["data"]]
    assert titles == ["Favorited second", "Favorited first"]
