from datetime import UTC, datetime

import pytest

from app.core.config import settings
from app.models import ListingImage


async def test_create_report_requires_authentication(client, create_listing):
    listing = await create_listing()

    response = await client.post(
        "/api/v1/reports",
        json={"target_type": "listing", "target_id": str(listing.public_id), "reason": "Scam"},
    )

    assert response.status_code == 401


async def test_create_report_for_a_listing(client, create_user, create_listing, login_as):
    login_as(await create_user())
    listing = await create_listing(title="Faux MacBook")

    response = await client.post(
        "/api/v1/reports",
        json={"target_type": "listing", "target_id": str(listing.public_id), "reason": "Scam"},
    )

    assert response.status_code == 201
    body = response.json()
    assert body["target_type"] == "listing"
    assert body["target_id"] == str(listing.public_id)
    assert body["reason"] == "Scam"
    assert body["status"] == "open"


async def test_create_report_for_a_message(client, create_user, create_message, login_as):
    login_as(await create_user())
    message = await create_message()

    response = await client.post(
        "/api/v1/reports",
        json={"target_type": "message", "target_id": str(message.id), "reason": "Insulte"},
    )

    assert response.status_code == 201
    assert response.json()["target_id"] == str(message.id)


async def test_create_report_for_a_review(client, create_user, create_review, login_as):
    login_as(await create_user())
    review = await create_review()

    response = await client.post(
        "/api/v1/reports",
        json={"target_type": "review", "target_id": str(review.id), "reason": "Avis de vengeance"},
    )

    assert response.status_code == 201
    body = response.json()
    assert body["target_type"] == "review"
    assert body["target_id"] == str(review.id)
    assert body["status"] == "open"


async def test_create_report_returns_404_for_unknown_listing(client, create_user, login_as):
    login_as(await create_user())

    response = await client.post(
        "/api/v1/reports",
        json={
            "target_type": "listing",
            "target_id": "00000000-0000-0000-0000-000000000000",
            "reason": "Scam",
        },
    )

    assert response.status_code == 404


async def test_create_report_returns_404_for_malformed_target_id(client, create_user, login_as):
    login_as(await create_user())

    response = await client.post(
        "/api/v1/reports",
        json={"target_type": "listing", "target_id": "not-a-uuid", "reason": "Scam"},
    )

    assert response.status_code == 404


async def test_create_report_returns_404_for_already_deleted_listing(
    client, create_user, create_listing, login_as
):
    login_as(await create_user())
    listing = await create_listing(status="deleted")

    response = await client.post(
        "/api/v1/reports",
        json={"target_type": "listing", "target_id": str(listing.public_id), "reason": "Scam"},
    )

    assert response.status_code == 404


async def test_create_report_returns_404_for_already_deleted_user(
    client, create_user, login_as
):
    login_as(await create_user())
    deleted = await create_user(deleted_at=datetime.now(UTC))

    response = await client.post(
        "/api/v1/reports",
        json={"target_type": "user", "target_id": str(deleted.public_id), "reason": "..."},
    )

    assert response.status_code == 404


async def test_create_report_returns_404_for_already_deleted_message(
    client, create_user, create_message, login_as
):
    login_as(await create_user())
    message = await create_message(deleted_at=datetime.now(UTC))

    response = await client.post(
        "/api/v1/reports",
        json={"target_type": "message", "target_id": str(message.id), "reason": "..."},
    )

    assert response.status_code == 404


async def test_create_report_returns_404_for_already_deleted_review(
    client, create_user, create_review, login_as
):
    login_as(await create_user())
    review = await create_review(deleted_at=datetime.now(UTC))

    response = await client.post(
        "/api/v1/reports",
        json={"target_type": "review", "target_id": str(review.id), "reason": "..."},
    )

    assert response.status_code == 404


async def test_resolve_report_delete_target_override_returns_404_for_already_deleted_target(
    client, create_user, create_listing, create_report, login_as
):
    login_as(await create_user(role="moderator"))
    already_deleted = await create_listing(status="deleted")
    report = await create_report()  # a different, still-active listing

    response = await client.post(
        f"/api/v1/reports/{report.id}/resolve",
        json={
            "action": "delete_target",
            "target_type": "listing",
            "target_id": str(already_deleted.public_id),
        },
    )

    assert response.status_code == 404


async def test_create_report_returns_400_for_self_report(client, create_user, login_as):
    me = await create_user()
    login_as(me)

    response = await client.post(
        "/api/v1/reports",
        json={"target_type": "user", "target_id": str(me.public_id), "reason": "..."},
    )

    assert response.status_code == 400


async def test_create_report_returns_409_for_duplicate_open_report_on_same_target(
    client, create_user, create_listing, login_as
):
    login_as(await create_user())
    listing = await create_listing()
    payload = {"target_type": "listing", "target_id": str(listing.public_id), "reason": "Scam"}
    first = await client.post("/api/v1/reports", json=payload)
    assert first.status_code == 201

    second = await client.post("/api/v1/reports", json=payload)

    assert second.status_code == 409


async def test_create_report_allows_a_new_report_once_the_previous_one_is_resolved(
    client, create_user, create_listing, login_as
):
    reporter = await create_user()
    login_as(reporter)
    listing = await create_listing()
    payload = {"target_type": "listing", "target_id": str(listing.public_id), "reason": "Scam"}
    first = await client.post("/api/v1/reports", json=payload)
    report_id = first.json()["id"]

    login_as(await create_user(role="moderator"))
    reject = await client.post(f"/api/v1/reports/{report_id}/reject")
    assert reject.status_code == 200

    login_as(reporter)
    second = await client.post("/api/v1/reports", json=payload)

    assert second.status_code == 201


async def test_create_report_allows_different_users_to_report_the_same_target(
    client, create_user, create_listing, login_as
):
    listing = await create_listing()
    payload = {"target_type": "listing", "target_id": str(listing.public_id), "reason": "Scam"}
    login_as(await create_user())
    first = await client.post("/api/v1/reports", json=payload)
    assert first.status_code == 201

    login_as(await create_user())
    second = await client.post("/api/v1/reports", json=payload)

    assert second.status_code == 201


async def test_list_reports_requires_authentication(client):
    response = await client.get("/api/v1/reports")

    assert response.status_code == 401


async def test_list_reports_returns_403_for_a_regular_user(client, create_user, login_as):
    login_as(await create_user())

    response = await client.get("/api/v1/reports")

    assert response.status_code == 403


async def test_list_reports_returns_reporter_and_target_for_a_moderator(
    client, create_user, create_listing, create_report, login_as
):
    login_as(await create_user(role="moderator"))
    reporter = await create_user(display_name="Alice")
    seller = await create_user(display_name="Bob le vendeur")
    listing = await create_listing(title="Vélo volé", seller_id=seller.id)
    await create_report(reporter_id=reporter.id, target_type="listing", target_id=listing.id)

    response = await client.get("/api/v1/reports")

    assert response.status_code == 200
    body = response.json()
    assert len(body) == 1
    assert body[0]["reporter"]["display_name"] == "Alice"
    assert body[0]["target"]["title"] == "Vélo volé"
    assert body[0]["target"]["seller"]["display_name"] == "Bob le vendeur"
    assert body[0]["target"]["seller"]["public_id"] == str(seller.public_id)


async def test_list_reports_exposes_the_message_sender(
    client, create_user, create_message, create_report, login_as
):
    # The block_user action needs a real user id: for a message-type report
    # that's the sender, not the message's own (non-user) id.
    login_as(await create_user(role="moderator"))
    sender = await create_user(display_name="Casey")
    message = await create_message(sender_id=sender.id)
    await create_report(target_type="message", target_id=message.id)

    response = await client.get("/api/v1/reports")

    assert response.json()[0]["target"]["sender"]["display_name"] == "Casey"


async def test_list_reports_filters_by_status(client, create_user, create_report, login_as):
    login_as(await create_user(role="admin"))
    await create_report(status="open")
    await create_report(status="closed")

    response = await client.get("/api/v1/reports", params={"status": "closed"})

    assert response.status_code == 200
    assert [r["status"] for r in response.json()] == ["closed"]


async def test_list_reports_returns_every_report(client, create_user, create_report, login_as):
    # The front builds its queues from this one list: a default page of 30
    # used to hide the oldest open reports.
    login_as(await create_user(role="moderator"))
    for _ in range(35):
        await create_report()

    response = await client.get("/api/v1/reports")

    assert response.status_code == 200
    assert len(response.json()) == 35


async def test_resolve_report_requires_moderator(client, create_user, create_report, login_as):
    login_as(await create_user())
    report = await create_report()

    response = await client.post(
        f"/api/v1/reports/{report.id}/resolve", json={"action": "delete_target"}
    )

    assert response.status_code == 403


async def test_resolve_report_returns_404_for_unknown_report(client, create_user, login_as):
    login_as(await create_user(role="moderator"))

    response = await client.post("/api/v1/reports/999999/resolve", json={"action": "delete_target"})

    assert response.status_code == 404


async def test_resolve_report_deletes_the_target_listing(
    client, db_session, create_user, create_listing, create_report, login_as
):
    login_as(await create_user(role="moderator"))
    listing = await create_listing()
    report = await create_report(target_type="listing", target_id=listing.id)

    response = await client.post(
        f"/api/v1/reports/{report.id}/resolve", json={"action": "delete_target"}
    )

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "resolved"
    assert body["closed_at"] is not None

    await db_session.refresh(listing)
    assert listing.status == "deleted"
    assert listing.deleted_at is not None


async def test_resolve_report_closes_sibling_reports_on_the_same_target(
    client, db_session, create_user, create_listing, create_report, login_as
):
    login_as(await create_user(role="moderator"))
    listing = await create_listing()
    report = await create_report(target_type="listing", target_id=listing.id)
    sibling = await create_report(target_type="listing", target_id=listing.id)
    other_target_report = await create_report()  # different listing - untouched

    response = await client.post(
        f"/api/v1/reports/{report.id}/resolve", json={"action": "delete_target"}
    )

    assert response.status_code == 200
    await db_session.refresh(sibling)
    assert sibling.status == "resolved"
    assert sibling.closed_at is not None
    await db_session.refresh(other_target_report)
    assert other_target_report.status == "open"


async def test_resolve_report_deletes_a_review_and_updates_subject_rating(
    client, db_session, create_user, create_review, create_report, login_as
):
    login_as(await create_user(role="moderator"))
    subject = await create_user(rating=5, rating_count=1)  # one prior 5-star review
    review = await create_review(subject_id=subject.id, rating=5)
    report = await create_report(target_type="review", target_id=review.id)

    response = await client.post(
        f"/api/v1/reports/{report.id}/resolve", json={"action": "delete_target"}
    )

    assert response.status_code == 200
    await db_session.refresh(review)
    assert review.deleted_at is not None
    await db_session.refresh(subject)
    assert subject.rating == 0
    assert subject.rating_count == 0


async def test_resolve_report_suspends_a_user(
    client, db_session, create_user, create_listing, create_report, login_as
):
    login_as(await create_user(role="moderator"))
    offender = await create_user()
    listing = await create_listing(seller_id=offender.id)
    report = await create_report(target_type="listing", target_id=listing.id)

    response = await client.post(
        f"/api/v1/reports/{report.id}/resolve",
        json={"action": "block_user", "user_id": str(offender.public_id)},
    )

    assert response.status_code == 200
    await db_session.refresh(offender)
    assert offender.is_active is False


async def test_resolve_report_block_user_returns_400_for_self_target(
    client, create_user, create_report, login_as
):
    moderator = await create_user(role="moderator")
    login_as(moderator)
    report = await create_report()

    response = await client.post(
        f"/api/v1/reports/{report.id}/resolve",
        json={"action": "block_user", "user_id": str(moderator.public_id)},
    )

    assert response.status_code == 400


async def test_resolve_report_block_user_returns_403_when_moderator_targets_moderator(
    client, create_user, create_report, login_as
):
    login_as(await create_user(role="moderator"))
    other_moderator = await create_user(role="moderator")
    report = await create_report()

    response = await client.post(
        f"/api/v1/reports/{report.id}/resolve",
        json={"action": "block_user", "user_id": str(other_moderator.public_id)},
    )

    assert response.status_code == 403


async def test_resolve_report_block_user_returns_403_when_moderator_targets_admin(
    client, create_user, create_report, login_as
):
    login_as(await create_user(role="moderator"))
    admin = await create_user(role="admin")
    report = await create_report()

    response = await client.post(
        f"/api/v1/reports/{report.id}/resolve",
        json={"action": "block_user", "user_id": str(admin.public_id)},
    )

    assert response.status_code == 403


async def test_resolve_report_block_user_allows_admin_to_target_moderator(
    client, db_session, create_user, create_report, login_as
):
    login_as(await create_user(role="admin"))
    moderator = await create_user(role="moderator")
    report = await create_report()

    response = await client.post(
        f"/api/v1/reports/{report.id}/resolve",
        json={"action": "block_user", "user_id": str(moderator.public_id)},
    )

    assert response.status_code == 200
    await db_session.refresh(moderator)
    assert moderator.is_active is False


async def test_resolve_report_block_user_requires_user_id(
    client, create_user, create_report, login_as
):
    login_as(await create_user(role="moderator"))
    report = await create_report()

    response = await client.post(
        f"/api/v1/reports/{report.id}/resolve", json={"action": "block_user"}
    )

    assert response.status_code == 422


async def test_resolve_report_delete_target_rejects_target_type_without_target_id(
    client, create_user, create_listing, create_report, login_as
):
    # target_type alone would resolve against the original report's internal
    # id, which belongs to a different table's id space than the override
    # type - e.g. reusing a listing's internal id to look up a "user" could
    # hit an unrelated account.
    login_as(await create_user(role="moderator"))
    listing = await create_listing()
    report = await create_report(target_type="listing", target_id=listing.id)

    response = await client.post(
        f"/api/v1/reports/{report.id}/resolve",
        json={"action": "delete_target", "target_type": "user"},
    )

    assert response.status_code == 422


async def test_resolve_report_returns_409_when_already_closed(
    client, create_user, create_report, login_as
):
    login_as(await create_user(role="moderator"))
    report = await create_report(status="resolved")

    response = await client.post(
        f"/api/v1/reports/{report.id}/resolve", json={"action": "delete_target"}
    )

    assert response.status_code == 409


async def test_reject_report_closes_it_without_sanction(
    client, create_user, create_report, login_as
):
    login_as(await create_user(role="moderator"))
    report = await create_report()

    response = await client.post(f"/api/v1/reports/{report.id}/reject")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "closed"
    assert body["closed_at"] is not None


async def test_reject_report_requires_moderator(client, create_user, create_report, login_as):
    login_as(await create_user())
    report = await create_report()

    response = await client.post(f"/api/v1/reports/{report.id}/reject")

    assert response.status_code == 403


async def test_reopen_report_sets_status_open(client, create_user, create_report, login_as):
    login_as(await create_user(role="moderator"))
    report = await create_report(status="closed")

    response = await client.post(f"/api/v1/reports/{report.id}/reopen")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "open"
    assert body["closed_at"] is None


async def test_reopen_report_unblock_user_requires_user_id(
    client, create_user, create_report, login_as
):
    login_as(await create_user(role="moderator"))
    report = await create_report(status="closed")

    response = await client.post(
        f"/api/v1/reports/{report.id}/reopen", json={"action": "unblock_user"}
    )

    assert response.status_code == 422


async def test_reopen_report_returns_409_when_not_closed(
    client, create_user, create_report, login_as
):
    login_as(await create_user(role="moderator"))
    report = await create_report(status="open")

    response = await client.post(f"/api/v1/reports/{report.id}/reopen")

    assert response.status_code == 409


async def test_reopen_report_can_unblock_a_user(
    client, db_session, create_user, create_report, login_as
):
    login_as(await create_user(role="moderator"))
    offender = await create_user(is_active=False)
    report = await create_report(status="resolved")

    response = await client.post(
        f"/api/v1/reports/{report.id}/reopen",
        json={"action": "unblock_user", "user_id": str(offender.public_id)},
    )

    assert response.status_code == 200
    await db_session.refresh(offender)
    assert offender.is_active is True


async def test_reopen_report_unblock_user_also_clears_deleted_at(
    client, db_session, create_user, create_report, login_as
):
    # delete_target on target_type="user" sets both is_active=False and
    # deleted_at - unblock_user must undo both, or the account stays
    # rejected by get_current_user's deleted_at filter despite the unblock.
    login_as(await create_user(role="moderator"))
    offender = await create_user(is_active=False, deleted_at=datetime.now(UTC))
    report = await create_report(status="resolved")

    response = await client.post(
        f"/api/v1/reports/{report.id}/reopen",
        json={"action": "unblock_user", "user_id": str(offender.public_id)},
    )

    assert response.status_code == 200
    await db_session.refresh(offender)
    assert offender.is_active is True
    assert offender.deleted_at is None


async def test_reopen_report_restore_target_restores_a_deleted_listing(
    client, db_session, create_user, create_listing, create_report, login_as
):
    login_as(await create_user(role="moderator"))
    listing = await create_listing(status="deleted", deleted_at=datetime.now(UTC))
    report = await create_report(target_type="listing", target_id=listing.id, status="resolved")

    response = await client.post(
        f"/api/v1/reports/{report.id}/reopen", json={"action": "restore_target"}
    )

    assert response.status_code == 200
    await db_session.refresh(listing)
    assert listing.status == "active"
    assert listing.deleted_at is None


async def test_reopen_report_restore_target_drops_images_whose_files_are_gone(
    client,
    db_session,
    create_user,
    create_listing,
    create_listing_image,
    create_report,
    login_as,
    tmp_path,
    monkeypatch,
):
    # The seller may have deleted the listing (and its files) themselves,
    # independently of this report - restoring must not bring back broken
    # image links.
    monkeypatch.setattr(settings, "media_root", str(tmp_path))
    login_as(await create_user(role="moderator"))
    seller = await create_user()
    listing = await create_listing(seller_id=seller.id, status="deleted", deleted_at=datetime.now(UTC))
    image = await create_listing_image(
        listing_id=listing.id, storage_path=f"/media/images/{seller.public_id}/{'a' * 32}.png"
    )
    report = await create_report(target_type="listing", target_id=listing.id, status="resolved")

    response = await client.post(
        f"/api/v1/reports/{report.id}/reopen", json={"action": "restore_target"}
    )

    assert response.status_code == 200
    await db_session.refresh(listing)
    assert listing.status == "active"
    assert await db_session.get(ListingImage, image.id) is None


async def test_reopen_report_restore_target_keeps_images_whose_files_still_exist(
    client,
    db_session,
    create_user,
    create_listing,
    create_listing_image,
    create_report,
    login_as,
    tmp_path,
    monkeypatch,
):
    monkeypatch.setattr(settings, "media_root", str(tmp_path))
    login_as(await create_user(role="moderator"))
    seller = await create_user()
    directory = tmp_path / "images" / str(seller.public_id)
    directory.mkdir(parents=True)
    (directory / ("a" * 32 + ".png")).write_bytes(b"fake")
    listing = await create_listing(seller_id=seller.id, status="deleted", deleted_at=datetime.now(UTC))
    image = await create_listing_image(
        listing_id=listing.id, storage_path=f"/media/images/{seller.public_id}/{'a' * 32}.png"
    )
    report = await create_report(target_type="listing", target_id=listing.id, status="resolved")

    response = await client.post(
        f"/api/v1/reports/{report.id}/reopen", json={"action": "restore_target"}
    )

    assert response.status_code == 200
    await db_session.refresh(listing)
    assert listing.status == "active"
    assert await db_session.get(ListingImage, image.id) is not None


async def test_reopen_report_restore_target_restores_a_deleted_message(
    client, db_session, create_user, create_message, create_report, login_as
):
    login_as(await create_user(role="moderator"))
    message = await create_message(deleted_at=datetime.now(UTC))
    report = await create_report(target_type="message", target_id=message.id, status="resolved")

    response = await client.post(
        f"/api/v1/reports/{report.id}/reopen", json={"action": "restore_target"}
    )

    assert response.status_code == 200
    await db_session.refresh(message)
    assert message.deleted_at is None


async def test_reopen_report_restore_target_restores_a_deleted_review_and_rating(
    client, db_session, create_user, create_review, create_report, login_as
):
    login_as(await create_user(role="moderator"))
    subject = await create_user(rating=0, rating_count=0)
    review = await create_review(subject_id=subject.id, rating=4, deleted_at=datetime.now(UTC))
    report = await create_report(target_type="review", target_id=review.id, status="resolved")

    response = await client.post(
        f"/api/v1/reports/{report.id}/reopen", json={"action": "restore_target"}
    )

    assert response.status_code == 200
    await db_session.refresh(review)
    assert review.deleted_at is None
    await db_session.refresh(subject)
    assert subject.rating == 4
    assert subject.rating_count == 1


async def test_reopen_report_restore_target_is_a_noop_when_not_deleted(
    client, db_session, create_user, create_listing, create_report, login_as
):
    login_as(await create_user(role="moderator"))
    listing = await create_listing(status="active")
    report = await create_report(target_type="listing", target_id=listing.id, status="resolved")

    response = await client.post(
        f"/api/v1/reports/{report.id}/reopen", json={"action": "restore_target"}
    )

    assert response.status_code == 200
    await db_session.refresh(listing)
    assert listing.status == "active"


async def test_create_report_accepts_a_numeric_message_target_id(
    client, create_user, create_message, login_as
):
    login_as(await create_user())
    message = await create_message()

    response = await client.post(
        "/api/v1/reports",
        json={"target_type": "message", "target_id": message.id, "reason": "Insulte"},
    )

    assert response.status_code == 201
    assert response.json()["target_id"] == str(message.id)


@pytest.mark.parametrize("target_id", [None, True, 1.5, {"id": 1}])
async def test_create_report_returns_422_for_a_non_string_non_int_target_id(
    client, create_user, login_as, target_id
):
    login_as(await create_user())

    response = await client.post(
        "/api/v1/reports",
        json={"target_type": "message", "target_id": target_id, "reason": "Insulte"},
    )

    assert response.status_code == 422


async def test_resolve_report_accepts_a_numeric_target_id_override(
    client, db_session, create_user, create_message, create_report, login_as
):
    login_as(await create_user(role="moderator"))
    report = await create_report()
    message = await create_message()

    response = await client.post(
        f"/api/v1/reports/{report.id}/resolve",
        json={"action": "delete_target", "target_type": "message", "target_id": message.id},
    )

    assert response.status_code == 200
    await db_session.refresh(message)
    assert message.deleted_at is not None
