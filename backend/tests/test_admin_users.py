"""Admin-only user management: GET /users, PATCH /users/{id}/role, DELETE /users/{id}."""

from datetime import UTC, datetime

import pytest
from sqlalchemy import select

from app.main import app
from app.models import Friend, FriendMessage, Listing, Message, Review, User
from app.realtime import get_hub


@pytest.fixture
async def admin(create_user, login_as):
    user = await create_user(role="admin")
    login_as(user)
    return user


# ── who may call them ─────────────────────────────────────────────


@pytest.mark.parametrize(
    ("method", "path"),
    [
        ("get", "/api/v1/users"),
        ("patch", "/api/v1/users/00000000-0000-0000-0000-000000000000/role"),
        ("delete", "/api/v1/users/00000000-0000-0000-0000-000000000000"),
    ],
)
async def test_anonymous_gets_401(client, method, path):
    response = await client.request(method, path, json={"role": "user"} if method == "patch" else None)

    assert response.status_code == 401


@pytest.mark.parametrize("role", ["user", "moderator"])
@pytest.mark.parametrize(
    ("method", "path"),
    [
        ("get", "/api/v1/users"),
        ("patch", "/api/v1/users/00000000-0000-0000-0000-000000000000/role"),
        ("delete", "/api/v1/users/00000000-0000-0000-0000-000000000000"),
    ],
)
async def test_only_an_admin_may_call_them(client, create_user, login_as, role, method, path):
    login_as(await create_user(role=role))

    response = await client.request(method, path, json={"role": "user"} if method == "patch" else None)

    assert response.status_code == 403


# ── GET /users ────────────────────────────────────────────────────


async def test_list_users_returns_roles_newest_first_without_email(
    client, admin, create_user
):
    older = await create_user(display_name="Older", created_at=datetime(2026, 1, 1, tzinfo=UTC))
    newer = await create_user(display_name="Newer", role="moderator")

    response = await client.get("/api/v1/users")

    assert response.status_code == 200
    body = response.json()
    names = [u["display_name"] for u in body["data"]]
    assert names.index("Newer") < names.index("Older")
    row = next(u for u in body["data"] if u["public_id"] == str(newer.public_id))
    assert row["role"] == "moderator"
    assert set(row) == {"public_id", "display_name", "role", "is_active", "created_at", "deleted_at"}
    assert older.email not in response.text


async def test_list_users_includes_suspended_and_soft_deleted_accounts(client, admin, create_user):
    suspended = await create_user(is_active=False)
    gone = await create_user(deleted_at=datetime.now(UTC))

    rows = {u["public_id"]: u for u in (await client.get("/api/v1/users")).json()["data"]}

    assert rows[str(suspended.public_id)]["is_active"] is False
    assert rows[str(gone.public_id)]["deleted_at"] is not None


async def test_list_users_filters_by_role(client, admin, create_user):
    moderator = await create_user(role="moderator")
    await create_user()

    response = await client.get("/api/v1/users", params={"role": "moderator"})

    assert [u["public_id"] for u in response.json()["data"]] == [str(moderator.public_id)]


async def test_list_users_searches_the_display_name_case_insensitively(client, admin, create_user):
    match = await create_user(display_name="Camille Durand")
    await create_user(display_name="Someone else")

    response = await client.get("/api/v1/users", params={"q": "camille"})

    assert [u["public_id"] for u in response.json()["data"]] == [str(match.public_id)]


async def test_a_percent_sign_in_the_search_is_literal(client, admin, create_user):
    literal = await create_user(display_name="100% legit")
    await create_user(display_name="Plain name")

    response = await client.get("/api/v1/users", params={"q": "%"})

    assert [u["public_id"] for u in response.json()["data"]] == [str(literal.public_id)]


async def test_list_users_is_paginated(client, admin, create_user):
    for _ in range(4):
        await create_user()

    first = (await client.get("/api/v1/users", params={"limit": 2, "page": 1})).json()
    last = (await client.get("/api/v1/users", params={"limit": 2, "page": 3})).json()

    assert first["total"] == 5  # the four plus the admin
    assert first["total_pages"] == 3
    assert len(first["data"]) == 2
    assert len(last["data"]) == 1


async def test_list_users_limit_is_capped(client, admin):
    assert (await client.get("/api/v1/users", params={"limit": 101})).status_code == 422


# ── PATCH /users/{id}/role ────────────────────────────────────────


async def test_admin_promotes_a_user_and_it_applies_at_once(
    client, admin, create_user, login_as, db_session
):
    target = await create_user()

    response = await client.patch(f"/api/v1/users/{target.public_id}/role", json={"role": "moderator"})

    assert response.status_code == 200
    assert response.json()["role"] == "moderator"
    await db_session.refresh(target)
    assert target.role == "moderator"
    # no new login needed: the role is read from the database on each request
    login_as(target)
    assert (await client.get("/api/v1/reports")).status_code == 200


async def test_admin_can_demote_another_admin(client, admin, create_user, db_session):
    other = await create_user(role="admin")

    response = await client.patch(f"/api/v1/users/{other.public_id}/role", json={"role": "user"})

    assert response.status_code == 200
    await db_session.refresh(other)
    assert other.role == "user"


async def test_setting_the_role_a_user_already_has_is_a_no_op(client, admin, create_user):
    target = await create_user(role="moderator")

    response = await client.patch(f"/api/v1/users/{target.public_id}/role", json={"role": "moderator"})

    assert response.status_code == 200


async def test_nobody_changes_their_own_role(client, admin, db_session):
    response = await client.patch(f"/api/v1/users/{admin.public_id}/role", json={"role": "user"})

    assert response.status_code == 400
    await db_session.refresh(admin)
    assert admin.role == "admin"


async def test_unknown_role_is_refused(client, admin, create_user):
    target = await create_user()

    response = await client.patch(f"/api/v1/users/{target.public_id}/role", json={"role": "superhero"})

    assert response.status_code == 422


async def test_role_change_on_an_unknown_or_soft_deleted_user_is_404(client, admin, create_user):
    gone = await create_user(deleted_at=datetime.now(UTC))

    unknown = await client.patch(
        "/api/v1/users/00000000-0000-0000-0000-000000000000/role", json={"role": "user"}
    )
    deleted = await client.patch(f"/api/v1/users/{gone.public_id}/role", json={"role": "admin"})

    assert (unknown.status_code, deleted.status_code) == (404, 404)


# ── DELETE /users/{id} ────────────────────────────────────────────


async def test_delete_user_removes_the_row_and_answers_204(client, admin, create_user, db_session):
    target = await create_user()

    response = await client.delete(f"/api/v1/users/{target.public_id}")

    assert response.status_code == 204
    assert await db_session.scalar(select(User).where(User.id == target.id)) is None


async def test_delete_user_logs_but_does_not_fail_when_uploads_cannot_be_removed(
    client, admin, create_user, db_session, monkeypatch, caplog
):
    def failing_rmtree(path, **kwargs):
        raise OSError("disk unavailable")

    target = await create_user()
    monkeypatch.setattr("shutil.rmtree", failing_rmtree)

    response = await client.delete(f"/api/v1/users/{target.public_id}")

    assert response.status_code == 204
    assert await db_session.scalar(select(User).where(User.id == target.id)) is None
    assert "could not remove uploads" in caplog.text


async def test_delete_user_does_not_log_when_nothing_was_ever_uploaded(
    client, admin, create_user, db_session, caplog
):
    # The default test media_root has no directory for this (freshly created)
    # user - that must stay a quiet no-op, not something worth logging.
    target = await create_user()

    response = await client.delete(f"/api/v1/users/{target.public_id}")

    assert response.status_code == 204
    assert "could not remove uploads" not in caplog.text


async def test_nobody_deletes_themselves(client, admin, db_session):
    response = await client.delete(f"/api/v1/users/{admin.public_id}")

    assert response.status_code == 400
    assert await db_session.scalar(select(User).where(User.id == admin.id)) is not None


async def test_delete_an_unknown_user_is_404(client, admin):
    response = await client.delete("/api/v1/users/00000000-0000-0000-0000-000000000000")

    assert response.status_code == 404


async def test_a_soft_deleted_account_can_be_deleted_for_real(client, admin, create_user, db_session):
    gone = await create_user(deleted_at=datetime.now(UTC))

    response = await client.delete(f"/api/v1/users/{gone.public_id}")

    assert response.status_code == 204
    assert await db_session.scalar(select(User).where(User.id == gone.id)) is None


async def test_delete_cascades_to_what_belongs_to_the_user(
    client, admin, create_user, create_listing, create_conversation, create_message,
    create_friend, db_session
):
    target = await create_user()
    other = await create_user()
    listing = await create_listing(seller_id=target.id)
    conversation = await create_conversation(listing_id=listing.id, buyer_id=other.id)
    message = await create_message(conversation_id=conversation.id, sender_id=other.id)
    friendship = await create_friend(requester_id=target.id, address_id=other.id, status="accepted")
    db_session.add(FriendMessage(conversation_id=friendship.id, sender_id=other.id, body="hi"))
    await db_session.flush()

    await client.delete(f"/api/v1/users/{target.public_id}")

    assert await db_session.scalar(select(Listing).where(Listing.id == listing.id)) is None
    # the other person's messages went with the conversation about the deleted seller's listing
    assert await db_session.scalar(select(Message).where(Message.id == message.id)) is None
    assert await db_session.scalar(select(Friend).where(Friend.id == friendship.id)) is None
    assert (await db_session.scalars(select(FriendMessage))).all() == []
    assert await db_session.scalar(select(User).where(User.id == other.id)) is not None


async def test_a_listing_the_user_bought_stays_with_no_buyer(
    client, admin, create_user, create_listing, db_session
):
    buyer = await create_user()
    bought = await create_listing(status="sold", buyer_id=buyer.id)

    await client.delete(f"/api/v1/users/{buyer.public_id}")

    await db_session.refresh(bought)
    assert bought.buyer_id is None
    assert bought.status == "sold"


async def test_reviews_written_by_the_user_leave_the_rating_of_the_reviewed_people(
    client, admin, create_user, create_review, db_session
):
    author = await create_user()
    subject = await create_user(rating=9, rating_count=2)  # a 4 (from the author) and a 5
    await create_review(author_id=author.id, subject_id=subject.id, rating=4)
    # a review already removed by moderation was taken out of the counters then
    await create_review(
        author_id=author.id, subject_id=subject.id, rating=1, deleted_at=datetime.now(UTC)
    )

    await client.delete(f"/api/v1/users/{author.public_id}")

    await db_session.refresh(subject)
    assert (subject.rating, subject.rating_count) == (5, 1)
    assert await db_session.scalar(select(Review).where(Review.author_id == author.id)) is None


async def test_reviews_received_by_the_user_go_without_touching_anyone_else(
    client, admin, create_user, create_review, db_session
):
    author = await create_user(rating=7, rating_count=3)
    subject = await create_user()
    await create_review(author_id=author.id, subject_id=subject.id, rating=5)

    await client.delete(f"/api/v1/users/{subject.public_id}")

    await db_session.refresh(author)
    assert (author.rating, author.rating_count) == (7, 3)


async def test_the_deleted_users_session_stops_working_and_sockets_are_closed(
    client, admin, create_user, login_as
):
    target = await create_user()
    closed = []

    class FakeRegistry:
        def close_principal(self, principal):
            closed.append(principal)

    class FakeHub:
        registry = FakeRegistry()

    app.dependency_overrides[get_hub] = lambda: FakeHub()
    try:
        await client.delete(f"/api/v1/users/{target.public_id}")
    finally:
        app.dependency_overrides.pop(get_hub, None)
    login_as(target)

    assert closed == [str(target.public_id)]
    # the session no longer resolves to a user, so /users/me answers anonymously (204)
    assert (await client.get("/api/v1/users/me")).status_code == 204
