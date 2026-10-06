from datetime import UTC, datetime

from app.models import UserBlock


async def test_create_listing_conversation_requires_authentication(client, create_listing):
    listing = await create_listing()

    response = await client.post(
        "/api/v1/conversations/listing", json={"listing_id": str(listing.public_id)}
    )

    assert response.status_code == 401


async def test_create_listing_conversation_creates_participants(client, create_listing, create_user, login_as):
    login_as(await create_user())
    listing = await create_listing(title="Clavier mécanique")

    response = await client.post(
        "/api/v1/conversations/listing", json={"listing_id": str(listing.public_id)}
    )

    assert response.status_code == 201
    body = response.json()
    assert body["type"] == "listing"
    assert body["listing_title"] == "Clavier mécanique"
    assert body["listing_public_id"] == str(listing.public_id)
    assert body["other_participant"]["display_name"] == "Test User"
    assert body["is_closed"] is False
    assert body["last_message"] is None


async def test_create_listing_conversation_is_idempotent(client, create_listing, create_user, login_as):
    login_as(await create_user())
    listing = await create_listing()

    first = await client.post(
        "/api/v1/conversations/listing", json={"listing_id": str(listing.public_id)}
    )
    second = await client.post(
        "/api/v1/conversations/listing", json={"listing_id": str(listing.public_id)}
    )

    assert first.json()["id"] == second.json()["id"]


async def test_create_listing_conversation_returns_404_for_unknown_listing(client, create_user, login_as):
    login_as(await create_user())

    response = await client.post(
        "/api/v1/conversations/listing",
        json={"listing_id": "00000000-0000-0000-0000-000000000000"},
    )

    assert response.status_code == 404


async def test_create_listing_conversation_returns_400_for_own_listing(client, create_user, create_listing, login_as):
    me = await create_user()
    login_as(me)
    listing = await create_listing(seller_id=me.id)

    response = await client.post(
        "/api/v1/conversations/listing", json={"listing_id": str(listing.public_id)}
    )

    assert response.status_code == 400


async def test_create_listing_conversation_returns_403_when_blocked(
    client, db_session, create_user, create_listing, login_as
):
    me = await create_user()
    login_as(me)
    seller = await create_user()
    listing = await create_listing(seller_id=seller.id)
    db_session.add(UserBlock(user_blocking=seller.id, user_blocked=me.id))
    await db_session.flush()

    response = await client.post(
        "/api/v1/conversations/listing", json={"listing_id": str(listing.public_id)}
    )

    assert response.status_code == 403


async def test_send_message_persists_and_appears_in_history(
    client, create_user, create_conversation, login_as
):
    me = await create_user()
    login_as(me)
    conversation = await create_conversation(buyer_id=me.id)

    response = await client.post(
        f"/api/v1/conversations/{conversation.id}/messages", json={"body": "Bonjour, toujours dispo ?"}
    )

    assert response.status_code == 201
    body = response.json()
    assert body["body"] == "Bonjour, toujours dispo ?"
    assert body["sender_id"] == str(me.public_id)

    history = await client.get(f"/api/v1/conversations/{conversation.id}/messages")
    assert history.status_code == 200
    assert [m["body"] for m in history.json()] == ["Bonjour, toujours dispo ?"]


async def test_send_message_returns_404_when_not_a_participant(client, create_conversation, create_user, login_as):
    login_as(await create_user())
    conversation = await create_conversation()

    response = await client.post(
        f"/api/v1/conversations/{conversation.id}/messages", json={"body": "Hello"}
    )

    assert response.status_code == 404


async def test_send_message_returns_409_when_conversation_is_closed(
    client, create_user, create_conversation, login_as
):
    me = await create_user()
    login_as(me)
    conversation = await create_conversation(buyer_id=me.id, closed=True)

    response = await client.post(
        f"/api/v1/conversations/{conversation.id}/messages", json={"body": "Hello"}
    )

    assert response.status_code == 409


async def test_send_message_returns_403_when_recipient_blocked_sender(
    client, db_session, create_user, create_conversation, login_as
):
    buyer = await create_user()
    login_as(buyer)
    conversation = await create_conversation(buyer_id=buyer.id)
    db_session.add(UserBlock(user_blocking=conversation.seller_id, user_blocked=buyer.id))
    await db_session.flush()

    response = await client.post(
        f"/api/v1/conversations/{conversation.id}/messages", json={"body": "Hello"}
    )

    assert response.status_code == 403


async def test_send_message_returns_403_when_sender_blocked_recipient(
    client, db_session, create_user, create_conversation, login_as
):
    buyer = await create_user()
    login_as(buyer)
    conversation = await create_conversation(buyer_id=buyer.id)
    db_session.add(UserBlock(user_blocking=buyer.id, user_blocked=conversation.seller_id))
    await db_session.flush()

    response = await client.post(
        f"/api/v1/conversations/{conversation.id}/messages", json={"body": "Hello"}
    )

    assert response.status_code == 403


async def test_list_messages_paginates_with_before_id(
    client, create_user, create_conversation, create_message, login_as
):
    me = await create_user()
    login_as(me)
    conversation = await create_conversation(buyer_id=me.id)
    first = await create_message(conversation_id=conversation.id, body="First")
    await create_message(conversation_id=conversation.id, body="Second")

    response = await client.get(
        f"/api/v1/conversations/{conversation.id}/messages", params={"before_id": first.id + 1}
    )

    bodies = [m["body"] for m in response.json()]
    assert "First" in bodies


async def test_close_conversation_sets_closed_for_current_user(
    client, create_user, create_conversation, login_as
):
    me = await create_user()
    login_as(me)
    conversation = await create_conversation(buyer_id=me.id)

    response = await client.delete(f"/api/v1/conversations/{conversation.id}")

    assert response.status_code == 204

    listing_conv = await client.get("/api/v1/conversations")
    matching = [c for c in listing_conv.json() if c["id"] == conversation.id]
    assert matching[0]["is_closed"] is True


async def test_close_conversation_returns_404_when_not_a_participant(client, create_conversation, create_user, login_as):
    login_as(await create_user())
    conversation = await create_conversation()

    response = await client.delete(f"/api/v1/conversations/{conversation.id}")

    assert response.status_code == 404


async def test_list_conversations_returns_only_current_user_conversations(
    client, create_user, create_conversation, login_as
):
    me = await create_user()
    login_as(me)
    mine = await create_conversation(buyer_id=me.id)
    await create_conversation()  # not mine

    response = await client.get("/api/v1/conversations")

    ids = [c["id"] for c in response.json()]
    assert ids == [mine.id]


async def test_list_conversations_includes_last_message(
    client, create_user, create_conversation, create_message, login_as
):
    me = await create_user()
    login_as(me)
    conversation = await create_conversation(buyer_id=me.id)
    await create_message(conversation_id=conversation.id, body="Old message")
    await create_message(conversation_id=conversation.id, body="Newest message")

    response = await client.get("/api/v1/conversations")

    assert response.json()[0]["last_message"]["body"] == "Newest message"


async def test_mark_sold_requires_authentication(client, create_conversation):
    conversation = await create_conversation()

    response = await client.post(f"/api/v1/conversations/{conversation.id}/mark-sold")

    assert response.status_code == 401


async def test_mark_sold_returns_404_when_not_a_participant(client, create_conversation, create_user, login_as):
    login_as(await create_user())
    conversation = await create_conversation()

    response = await client.post(f"/api/v1/conversations/{conversation.id}/mark-sold")

    assert response.status_code == 404


async def test_mark_sold_returns_403_for_buyer(client, create_user, create_conversation, login_as):
    buyer = await create_user()
    login_as(buyer)
    conversation = await create_conversation(buyer_id=buyer.id)

    response = await client.post(f"/api/v1/conversations/{conversation.id}/mark-sold")

    assert response.status_code == 403


async def test_mark_sold_sets_listing_status_and_buyer(
    client, create_user, create_listing, create_conversation, login_as
):
    seller = await create_user()
    buyer = await create_user()
    login_as(seller)
    listing = await create_listing(seller_id=seller.id)
    conversation = await create_conversation(listing_id=listing.id, buyer_id=buyer.id)

    response = await client.post(f"/api/v1/conversations/{conversation.id}/mark-sold")

    assert response.status_code == 200
    body = response.json()
    assert body["listing_status"] == "sold"
    assert body["listing_seller_id"] == str(seller.public_id)
    assert body["listing_buyer_id"] == str(buyer.public_id)
    assert body["has_reviewed"] is False

    listing_response = await client.get(f"/api/v1/listings/{listing.public_id}")
    assert listing_response.json()["status"] == "sold"


async def test_mark_sold_sets_listing_updated_at(
    client, create_user, create_listing, create_conversation, login_as
):
    seller = await create_user()
    login_as(seller)
    listing = await create_listing(seller_id=seller.id)
    conversation = await create_conversation(listing_id=listing.id)
    before = datetime.now(UTC)

    response = await client.post(f"/api/v1/conversations/{conversation.id}/mark-sold")

    assert response.status_code == 200
    listing_response = await client.get(f"/api/v1/listings/{listing.public_id}")
    updated_at = listing_response.json()["updated_at"]
    assert updated_at is not None
    assert datetime.fromisoformat(updated_at) >= before


async def test_mark_sold_reports_has_reviewed_true(
    client, create_user, create_listing, create_conversation, create_review, login_as
):
    seller = await create_user()
    buyer = await create_user()
    login_as(seller)
    listing = await create_listing(seller_id=seller.id)
    conversation = await create_conversation(listing_id=listing.id, buyer_id=buyer.id)
    await create_review(conversation_id=conversation.id, author_id=buyer.id, subject_id=seller.id)

    response = await client.post(f"/api/v1/conversations/{conversation.id}/mark-sold")

    assert response.json()["has_reviewed"] is True


async def test_mark_sold_returns_409_when_listing_already_sold(
    client, db_session, create_user, create_listing, create_conversation, login_as
):
    # A seller can have several conversations for the same listing (buyers
    # who only asked questions). Once sold via one, marking it sold again
    # from another must not silently reassign listings.buyer_id.
    seller = await create_user()
    first_buyer = await create_user()
    second_buyer = await create_user()
    login_as(seller)
    listing = await create_listing(seller_id=seller.id)
    first_conversation = await create_conversation(listing_id=listing.id, buyer_id=first_buyer.id)
    second_conversation = await create_conversation(listing_id=listing.id, buyer_id=second_buyer.id)

    first = await client.post(f"/api/v1/conversations/{first_conversation.id}/mark-sold")
    assert first.status_code == 200
    await db_session.refresh(listing)
    sold_at = listing.updated_at

    second = await client.post(f"/api/v1/conversations/{second_conversation.id}/mark-sold")

    assert second.status_code == 409
    await db_session.refresh(listing)
    assert listing.buyer_id == first_buyer.id
    assert listing.updated_at == sold_at


async def test_list_conversations_exposes_transaction_fields_for_an_active_listing(
    client, create_user, create_listing, create_conversation, login_as
):
    seller = await create_user()
    buyer = await create_user()
    listing = await create_listing(seller_id=seller.id)
    await create_conversation(listing_id=listing.id, buyer_id=buyer.id)

    for viewer in (buyer, seller):
        login_as(viewer)
        [item] = (await client.get("/api/v1/conversations")).json()
        assert item["listing_status"] == "active"
        assert item["listing_seller_id"] == str(seller.public_id)
        assert item["listing_buyer_id"] is None
        assert item["has_reviewed"] is False


async def test_list_conversations_exposes_the_buyer_only_on_the_conversation_it_was_sold_through(
    client, create_user, create_listing, create_conversation, login_as
):
    seller = await create_user()
    winner = await create_user()
    other_buyer = await create_user()
    listing = await create_listing(seller_id=seller.id, status="sold", buyer_id=winner.id)
    sold_through = await create_conversation(listing_id=listing.id, buyer_id=winner.id)
    other = await create_conversation(listing_id=listing.id, buyer_id=other_buyer.id)

    login_as(seller)
    by_id = {c["id"]: c for c in (await client.get("/api/v1/conversations")).json()}
    assert by_id[sold_through.id]["listing_status"] == "sold"
    assert by_id[sold_through.id]["listing_buyer_id"] == str(winner.public_id)
    assert by_id[other.id]["listing_status"] == "sold"
    assert by_id[other.id]["listing_buyer_id"] is None

    login_as(winner)
    [item] = (await client.get("/api/v1/conversations")).json()
    assert item["listing_buyer_id"] == str(winner.public_id)

    login_as(other_buyer)
    [item] = (await client.get("/api/v1/conversations")).json()
    assert item["listing_buyer_id"] is None


async def test_list_conversations_has_reviewed_only_tracks_the_buyer_review(
    client, create_user, create_listing, create_conversation, create_review, login_as
):
    seller = await create_user()
    buyer = await create_user()
    listing = await create_listing(seller_id=seller.id, status="sold", buyer_id=buyer.id)
    conversation = await create_conversation(listing_id=listing.id, buyer_id=buyer.id)

    await create_review(conversation_id=conversation.id, author_id=seller.id, subject_id=buyer.id)
    login_as(buyer)
    assert (await client.get("/api/v1/conversations")).json()[0]["has_reviewed"] is False

    await create_review(conversation_id=conversation.id, author_id=buyer.id, subject_id=seller.id)
    for viewer in (buyer, seller):
        login_as(viewer)
        assert (await client.get("/api/v1/conversations")).json()[0]["has_reviewed"] is True
