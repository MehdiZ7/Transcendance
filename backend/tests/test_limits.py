"""Size limits on client input (app/schemas/limits.py).

Each limit is tested at the edge: the largest accepted value passes, one more
is a 422 naming the field.
"""

import pytest
from sqlalchemy.exc import DBAPIError

from app.main import _unstorable_text
from app.schemas import limits


def _field(response) -> str:
    return response.json()["detail"][0]["loc"][-1]


# ── messages ──────────────────────────────────────────────────────


async def test_message_at_the_limit_is_accepted(client, create_user, create_conversation, login_as):
    me = await create_user()
    login_as(me)
    conversation = await create_conversation(buyer_id=me.id)

    response = await client.post(
        f"/api/v1/conversations/{conversation.id}/messages",
        json={"body": "a" * limits.MAX_MESSAGE_LENGTH},
    )

    assert response.status_code == 201


async def test_message_over_the_limit_is_refused(client, create_user, create_conversation, login_as):
    me = await create_user()
    login_as(me)
    conversation = await create_conversation(buyer_id=me.id)

    response = await client.post(
        f"/api/v1/conversations/{conversation.id}/messages",
        json={"body": "a" * (limits.MAX_MESSAGE_LENGTH + 1)},
    )

    assert response.status_code == 422
    assert _field(response) == "body"


async def test_message_of_spaces_is_refused(client, create_user, create_conversation, login_as):
    me = await create_user()
    login_as(me)
    conversation = await create_conversation(buyer_id=me.id)

    response = await client.post(
        f"/api/v1/conversations/{conversation.id}/messages", json={"body": "   \n  "}
    )

    assert response.status_code == 422


async def test_message_is_stored_without_surrounding_whitespace(
    client, create_user, create_conversation, login_as
):
    me = await create_user()
    login_as(me)
    conversation = await create_conversation(buyer_id=me.id)

    response = await client.post(
        f"/api/v1/conversations/{conversation.id}/messages", json={"body": "  salut \n"}
    )

    assert response.json()["body"] == "salut"


async def test_friend_message_over_the_limit_is_refused(client, create_user, create_friend, login_as):
    me = await create_user()
    login_as(me)
    other = await create_user()
    await create_friend(requester_id=me.id, address_id=other.id, status="accepted")

    response = await client.post(
        f"/api/v1/friends/{other.public_id}/messages",
        json={"body": "a" * (limits.MAX_MESSAGE_LENGTH + 1)},
    )

    assert response.status_code == 422


# ── reviews and reports ───────────────────────────────────────────


async def test_review_body_over_the_limit_is_refused(client, create_user, login_as):
    login_as(await create_user())

    response = await client.post(
        "/api/v1/reviews",
        json={
            "conversation_id": 1,
            "subject_id": "00000000-0000-0000-0000-000000000000",
            "rating": 5,
            "body": "a" * (limits.MAX_REVIEW_LENGTH + 1),
        },
    )

    assert response.status_code == 422
    assert _field(response) == "body"


async def test_review_conversation_id_above_bigint_is_refused(client, create_user, login_as):
    login_as(await create_user())

    response = await client.post(
        "/api/v1/reviews",
        json={
            "conversation_id": limits.MAX_DB_ID + 1,
            "subject_id": "00000000-0000-0000-0000-000000000000",
            "rating": 5,
        },
    )

    assert response.status_code == 422


async def test_report_reason_over_the_limit_is_refused(client, create_user, login_as):
    me = await create_user()
    login_as(me)
    target = await create_user()

    response = await client.post(
        "/api/v1/reports",
        json={
            "target_type": "user",
            "target_id": str(target.public_id),
            "reason": "a" * (limits.MAX_REPORT_REASON_LENGTH + 1),
        },
    )

    assert response.status_code == 422
    assert _field(response) == "reason"


async def test_report_target_id_over_the_limit_is_refused(client, create_user, login_as):
    login_as(await create_user())

    response = await client.post(
        "/api/v1/reports",
        json={
            "target_type": "message",
            "target_id": "1" * (limits.MAX_TARGET_ID_LENGTH + 1),
            "reason": "spam",
        },
    )

    assert response.status_code == 422
    assert _field(response) == "target_id"


# ── profile ───────────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("field", "size"),
    [
        ("bio", limits.MAX_BIO_LENGTH),
        ("display_name", limits.MAX_DISPLAY_NAME_LENGTH),
        ("avatar_path", limits.MAX_AVATAR_PATH_LENGTH),
    ],
)
async def test_profile_field_limit(client, create_user, login_as, field, size):
    login_as(await create_user())

    # an avatar has to be an allowed image reference as well as short enough
    prefix = "https://cdn.intra.42.fr/" if field == "avatar_path" else ""

    def value(length):
        return prefix + "a" * (length - len(prefix))

    at_limit = await client.patch("/api/v1/users/me", json={field: value(size)})
    over_limit = await client.patch("/api/v1/users/me", json={field: value(size + 1)})

    assert at_limit.status_code == 200
    assert over_limit.status_code == 422
    assert _field(over_limit) == field


async def test_profile_display_name_cannot_be_blank(client, create_user, login_as):
    login_as(await create_user())

    response = await client.patch("/api/v1/users/me", json={"display_name": "   "})

    assert response.status_code == 422


async def test_profile_bio_can_be_cleared(client, create_user, login_as):
    login_as(await create_user(bio="old"))

    response = await client.patch("/api/v1/users/me", json={"bio": ""})

    assert response.status_code == 200


# ── listings ──────────────────────────────────────────────────────


async def test_listing_at_every_limit_is_accepted(client, create_user, login_as, listing_payload):
    login_as(await create_user())
    payload = await listing_payload(
        title="t" * limits.MAX_LISTING_TITLE_LENGTH,
        body="b" * limits.MAX_LISTING_BODY_LENGTH,
        price=limits.MAX_PRICE,
        image_urls=["https://cdn.intra.42.fr/" + "a" * 470] * limits.MAX_IMAGES_PER_LISTING,
        attributes={f"k{i}": i for i in range(limits.MAX_ATTRIBUTES_KEYS)},
    )

    response = await client.post("/api/v1/listings", json=payload)

    assert response.status_code == 201


@pytest.mark.parametrize(
    ("override", "field"),
    [
        ({"title": "t" * (limits.MAX_LISTING_TITLE_LENGTH + 1)}, "title"),
        ({"title": "   "}, "title"),
        ({"body": "b" * (limits.MAX_LISTING_BODY_LENGTH + 1)}, "body"),
        ({"price": limits.MAX_PRICE + 1}, "price"),
        ({"price": -1}, "price"),
        ({"currency": "euro"}, "currency"),
        ({"category_id": limits.MAX_DB_ID + 1}, "category_id"),
        ({"location_id": 0}, "location_id"),
        ({"image_urls": ["https://cdn.intra.42.fr/a.jpg"] * (limits.MAX_IMAGES_PER_LISTING + 1)}, "image_urls"),
        ({"image_urls": ["https://cdn.intra.42.fr/" + "a" * limits.MAX_IMAGE_URL_LENGTH]}, 0),  # 0 = index in image_urls
        ({"attributes": {f"k{i}": i for i in range(limits.MAX_ATTRIBUTES_KEYS + 1)}}, "attributes"),
        ({"attributes": {"note": "x" * limits.MAX_ATTRIBUTES_BYTES}}, "attributes"),
    ],
)
async def test_listing_over_a_limit_is_refused(
    client, create_user, login_as, listing_payload, override, field
):
    login_as(await create_user())

    response = await client.post("/api/v1/listings", json=await listing_payload(**override))

    assert response.status_code == 422
    assert _field(response) == field


# ── routes: ids, pages, search ────────────────────────────────────


@pytest.mark.parametrize(
    "path",
    [
        f"/api/v1/conversations/{limits.MAX_DB_ID + 1}/messages",
        "/api/v1/conversations/0/messages",
        "/api/v1/conversations/1/messages?before_id=99999999999999999999",
        f"/api/v1/friends/{limits.MAX_DB_ID + 1}/accept",
    ],
)
async def test_id_outside_bigint_is_refused_not_a_database_error(client, create_user, login_as, path):
    login_as(await create_user())

    response = await (client.post(path) if path.endswith("/accept") else client.get(path))

    assert response.status_code == 422


@pytest.mark.parametrize(
    "path",
    [
        "/api/v1/listings?page=10001",
        "/api/v1/listings?page=0",
        f"/api/v1/listings?q={'a' * (limits.MAX_SEARCH_LENGTH + 1)}",
        f"/api/v1/listings?prix_max={limits.MAX_PRICE + 1}",
        f"/api/v1/listings?categorie={limits.MAX_DB_ID + 1}",
        "/api/v1/listings?limit=101",
    ],
)
async def test_listing_search_parameters_are_bounded(client, path):
    response = await client.get(path)

    assert response.status_code == 422


async def test_listing_search_at_the_limits_is_accepted(client):
    response = await client.get(
        f"/api/v1/listings?page={limits.MAX_PAGE}&q={'a' * limits.MAX_SEARCH_LENGTH}"
        f"&prix_max={limits.MAX_PRICE}&limit=100"
    )

    assert response.status_code == 200


# ── the NUL character: PostgreSQL cannot store it ─────────────────


async def test_message_with_a_nul_is_refused(client, create_user, create_conversation, login_as):
    me = await create_user()
    login_as(me)
    conversation = await create_conversation(buyer_id=me.id)

    response = await client.post(
        f"/api/v1/conversations/{conversation.id}/messages", json={"body": "a\x00b"}
    )

    assert response.status_code == 422
    assert _field(response) == "body"


@pytest.mark.parametrize("field", ["title", "body"])
async def test_listing_text_with_a_nul_is_refused(client, create_user, login_as, listing_payload, field):
    login_as(await create_user())

    response = await client.post("/api/v1/listings", json=await listing_payload(**{field: "a\x00b"}))

    assert response.status_code == 422
    assert _field(response) == field


@pytest.mark.parametrize("field", ["display_name", "bio"])
async def test_profile_text_with_a_nul_is_refused(client, create_user, login_as, field):
    login_as(await create_user())

    response = await client.patch("/api/v1/users/me", json={field: "a\x00b"})

    assert response.status_code == 422
    assert _field(response) == field


async def test_report_reason_with_a_nul_is_refused(client, create_user, create_listing, login_as):
    login_as(await create_user())
    listing = await create_listing()

    response = await client.post(
        "/api/v1/reports",
        json={"target_type": "listing", "target_id": str(listing.public_id), "reason": "a\x00b"},
    )

    assert response.status_code == 422
    assert _field(response) == "reason"


async def test_listing_search_with_a_nul_is_refused(client):
    response = await client.get("/api/v1/listings", params={"q": "a\x00b"})

    assert response.status_code == 422
    assert _field(response) == "q"


@pytest.mark.parametrize("param", ["q", "role"])
async def test_admin_user_search_with_a_nul_is_refused(client, create_user, login_as, param):
    login_as(await create_user(role="admin"))

    response = await client.get("/api/v1/users", params={param: "a\x00b"})

    assert response.status_code == 422
    assert _field(response) == param


# Fields without the NoNul rule reach the database: the handler in main.py
# answers 422 instead of the 500 PostgreSQL's refusal used to give.


async def test_listing_attributes_with_a_nul_are_refused(client, create_user, login_as, listing_payload):
    login_as(await create_user())

    response = await client.post(
        "/api/v1/listings", json=await listing_payload(attributes={"note": "a\x00b"})
    )

    assert response.status_code == 422


async def test_role_with_a_nul_is_refused(client, create_user, login_as):
    login_as(await create_user(role="admin"))
    target = await create_user()

    response = await client.patch(f"/api/v1/users/{target.public_id}/role", json={"role": "a\x00b"})

    assert response.status_code == 422


class _Orig(Exception):
    def __init__(self, sqlstate: str) -> None:
        super().__init__(sqlstate)
        self.sqlstate = sqlstate


async def test_other_database_errors_still_raise():
    # a unique violation (23505) must not turn into a 422
    error = DBAPIError("INSERT ...", {}, _Orig("23505"))

    with pytest.raises(DBAPIError):
        await _unstorable_text(None, error)
