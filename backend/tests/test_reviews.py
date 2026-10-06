async def test_create_review_requires_authentication(client, create_conversation, create_user):
    conversation = await create_conversation()
    subject = await create_user()

    response = await client.post(
        "/api/v1/reviews",
        json={"conversation_id": conversation.id, "subject_id": str(subject.public_id), "rating": 5},
    )

    assert response.status_code == 401


async def test_create_review_persists_and_updates_subject_rating(
    client, db_session, create_user, create_listing, create_conversation, login_as
):
    author = await create_user()
    login_as(author)
    subject = await create_user(rating=0, rating_count=0)
    listing = await create_listing(seller_id=subject.id, status="sold", buyer_id=author.id)
    conversation = await create_conversation(listing_id=listing.id, buyer_id=author.id)

    response = await client.post(
        "/api/v1/reviews",
        json={
            "conversation_id": conversation.id,
            "subject_id": str(subject.public_id),
            "rating": 4,
            "body": "Bon vendeur",
        },
    )

    assert response.status_code == 201
    body = response.json()
    assert body["rating"] == 4
    assert body["subject_id"] == str(subject.public_id)
    assert body["author_id"] == str(author.public_id)

    await db_session.refresh(subject)
    assert subject.rating == 4
    assert subject.rating_count == 1

    profile = await client.get(f"/api/v1/users/{subject.public_id}")
    assert profile.json()["rating"] == 4.0


async def test_create_review_returns_404_for_unknown_subject(client, create_conversation, create_user, login_as):
    login_as(await create_user())
    conversation = await create_conversation()

    response = await client.post(
        "/api/v1/reviews",
        json={
            "conversation_id": conversation.id,
            "subject_id": "00000000-0000-0000-0000-000000000000",
            "rating": 5,
        },
    )

    assert response.status_code == 404


async def test_create_review_returns_404_for_unknown_conversation(client, create_user, login_as):
    login_as(await create_user())
    subject = await create_user()

    response = await client.post(
        "/api/v1/reviews",
        json={"conversation_id": 999999, "subject_id": str(subject.public_id), "rating": 5},
    )

    assert response.status_code == 404


async def test_create_review_returns_400_for_self_review(client, create_user, create_conversation, login_as):
    me = await create_user()
    login_as(me)
    conversation = await create_conversation()

    response = await client.post(
        "/api/v1/reviews",
        json={
            "conversation_id": conversation.id,
            "subject_id": str(me.public_id),
            "rating": 5,
        },
    )

    assert response.status_code == 400


async def test_create_review_returns_403_when_not_a_participant(
    client, create_user, create_conversation, login_as
):
    login_as(await create_user())
    subject = await create_user()
    conversation = await create_conversation()  # random, unrelated buyer/seller

    response = await client.post(
        "/api/v1/reviews",
        json={"conversation_id": conversation.id, "subject_id": str(subject.public_id), "rating": 5},
    )

    assert response.status_code == 403


async def test_create_review_returns_400_when_subject_is_not_the_other_participant(
    client, create_user, create_listing, create_conversation, login_as
):
    author = await create_user()
    login_as(author)
    listing = await create_listing(status="sold")
    conversation = await create_conversation(listing_id=listing.id, buyer_id=author.id)
    unrelated = await create_user()  # a real user, but not this conversation's other side

    response = await client.post(
        "/api/v1/reviews",
        json={"conversation_id": conversation.id, "subject_id": str(unrelated.public_id), "rating": 5},
    )

    assert response.status_code == 400


async def test_create_review_returns_400_when_listing_not_sold(
    client, create_user, create_conversation, login_as
):
    author = await create_user()
    login_as(author)
    subject = await create_user()
    conversation = await create_conversation(buyer_id=author.id)  # listing defaults to "active"

    response = await client.post(
        "/api/v1/reviews",
        json={"conversation_id": conversation.id, "subject_id": str(subject.public_id), "rating": 5},
    )

    assert response.status_code == 400


async def test_create_review_returns_400_when_sold_via_a_different_conversation(
    client, create_user, create_listing, create_conversation, login_as
):
    # The listing is sold (via mark-sold on someone else's conversation), so
    # status == SOLD alone would pass - but this buyer never bought it.
    seller = await create_user()
    actual_buyer = await create_user()
    other_visitor = await create_user()
    login_as(other_visitor)
    listing = await create_listing(seller_id=seller.id, status="sold", buyer_id=actual_buyer.id)
    conversation = await create_conversation(listing_id=listing.id, buyer_id=other_visitor.id)

    response = await client.post(
        "/api/v1/reviews",
        json={"conversation_id": conversation.id, "subject_id": str(seller.public_id), "rating": 5},
    )

    assert response.status_code == 400


async def test_create_review_returns_409_for_duplicate_in_same_conversation(
    client, create_user, create_listing, create_conversation, login_as
):
    author = await create_user()
    login_as(author)
    subject = await create_user()
    listing = await create_listing(seller_id=subject.id, status="sold", buyer_id=author.id)
    conversation = await create_conversation(listing_id=listing.id, buyer_id=author.id)

    payload = {
        "conversation_id": conversation.id,
        "subject_id": str(subject.public_id),
        "rating": 3,
    }
    first = await client.post("/api/v1/reviews", json=payload)
    assert first.status_code == 201

    second = await client.post("/api/v1/reviews", json=payload)

    assert second.status_code == 409


async def test_create_review_rejects_out_of_range_rating(client, create_user, create_conversation, login_as):
    login_as(await create_user())
    subject = await create_user()
    conversation = await create_conversation()

    response = await client.post(
        "/api/v1/reviews",
        json={"conversation_id": conversation.id, "subject_id": str(subject.public_id), "rating": 6},
    )

    assert response.status_code == 422


async def test_delete_review_requires_authentication(client, create_review):
    review = await create_review()

    response = await client.delete(f"/api/v1/reviews/{review.id}")

    assert response.status_code == 401


async def test_delete_review_by_the_author_soft_deletes_and_updates_subject_rating(
    client, db_session, create_user, create_review, login_as
):
    author = await create_user()
    subject = await create_user(rating=4, rating_count=1)
    review = await create_review(author_id=author.id, subject_id=subject.id, rating=4)
    login_as(author)

    response = await client.delete(f"/api/v1/reviews/{review.id}")

    assert response.status_code == 204

    await db_session.refresh(review)
    assert review.deleted_at is not None

    await db_session.refresh(subject)
    assert subject.rating == 0
    assert subject.rating_count == 0

    listed = await client.get(f"/api/v1/users/{subject.public_id}/reviews")
    assert listed.json() == []


async def test_delete_review_by_an_unrelated_user_returns_403(
    client, create_user, create_review, login_as
):
    review = await create_review()
    login_as(await create_user())

    response = await client.delete(f"/api/v1/reviews/{review.id}")

    assert response.status_code == 403


async def test_delete_review_returns_404_for_unknown_review(client, create_user, login_as):
    login_as(await create_user())

    response = await client.delete("/api/v1/reviews/999999")

    assert response.status_code == 404


async def test_delete_review_twice_returns_404(client, create_user, create_review, login_as):
    author = await create_user()
    review = await create_review(author_id=author.id)
    login_as(author)

    first = await client.delete(f"/api/v1/reviews/{review.id}")
    second = await client.delete(f"/api/v1/reviews/{review.id}")

    assert first.status_code == 204
    assert second.status_code == 404
