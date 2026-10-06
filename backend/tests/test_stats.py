"""GET /users/me/stats."""

from datetime import UTC, datetime

import pytest


async def _stats(client):
    response = await client.get("/api/v1/users/me/stats")
    assert response.status_code == 200
    return response.json()


async def test_stats_require_authentication(client):
    response = await client.get("/api/v1/users/me/stats")

    assert response.status_code == 401


async def test_stats_of_a_user_with_nothing_are_zeros_and_empty_lists(
    client, create_user, login_as
):
    login_as(await create_user())

    assert await _stats(client) == {
        "selling": {
            "active": {"count": 0, "total_value": 0, "average_price": 0.0},
            "sold": {"count": 0, "total_value": 0, "average_price": 0.0},
            "by_category": [],
        },
        "buying": {"count": 0, "total_spent": 0, "average_price": 0.0, "by_category": []},
    }


async def test_selling_totals_and_averages_per_status(
    client, create_user, create_listing, login_as
):
    me = await create_user()
    login_as(me)
    await create_listing(seller_id=me.id, status="active", price=100)
    await create_listing(seller_id=me.id, status="active", price=201)
    await create_listing(seller_id=me.id, status="sold", price=50)

    selling = (await _stats(client))["selling"]

    assert selling["active"] == {"count": 2, "total_value": 301, "average_price": 150.5}
    assert selling["sold"] == {"count": 1, "total_value": 50, "average_price": 50.0}


async def test_average_is_rounded_to_two_decimals(client, create_user, create_listing, login_as):
    me = await create_user()
    login_as(me)
    for price in (1, 1, 2):
        await create_listing(seller_id=me.id, status="active", price=price)

    selling = (await _stats(client))["selling"]

    assert selling["active"]["average_price"] == 1.33


@pytest.mark.parametrize("status", ["draft", "expired", "archived", "deleted"])
async def test_selling_ignores_listings_that_are_neither_active_nor_sold(
    client, create_user, create_listing, login_as, status
):
    me = await create_user()
    login_as(me)
    await create_listing(seller_id=me.id, status=status, price=999)

    selling = (await _stats(client))["selling"]

    assert selling["active"]["count"] == 0
    assert selling["sold"]["count"] == 0
    assert selling["by_category"] == []


async def test_selling_ignores_soft_deleted_listings_whatever_their_status(
    client, create_user, create_listing, login_as
):
    me = await create_user()
    login_as(me)
    await create_listing(seller_id=me.id, status="sold", price=10, deleted_at=datetime.now(UTC))

    assert (await _stats(client))["selling"]["sold"]["count"] == 0


async def test_selling_ignores_other_sellers_listings(
    client, create_user, create_listing, login_as
):
    login_as(await create_user())
    await create_listing(status="active", price=500)

    assert (await _stats(client))["selling"]["active"]["count"] == 0


async def test_selling_by_category_splits_active_and_sold_and_sorts_biggest_first(
    client, create_user, create_listing, create_category, login_as
):
    me = await create_user()
    login_as(me)
    books = await create_category(category_name="Books")
    tech = await create_category(category_name="Tech")
    await create_listing(seller_id=me.id, status="active", category_id=books.id)
    await create_listing(seller_id=me.id, status="sold", category_id=tech.id)
    await create_listing(seller_id=me.id, status="active", category_id=tech.id)
    await create_listing(seller_id=me.id, status="active", category_id=tech.id)

    by_category = (await _stats(client))["selling"]["by_category"]

    assert by_category == [
        {"category_id": tech.id, "category_name": "Tech", "active": 2, "sold": 1},
        {"category_id": books.id, "category_name": "Books", "active": 1, "sold": 0},
    ]


async def test_an_uncategorised_listing_is_counted_like_any_category(
    client, create_user, create_listing, create_category, login_as
):
    me = await create_user()
    login_as(me)
    books = await create_category(category_name="Books")
    await create_listing(seller_id=me.id, status="active", category_id=None)
    await create_listing(seller_id=me.id, status="active", category_id=None)
    await create_listing(seller_id=me.id, status="active", category_id=books.id)

    by_category = (await _stats(client))["selling"]["by_category"]

    assert [(c["category_name"], c["active"]) for c in by_category] == [(None, 2), ("Books", 1)]


async def test_on_a_tie_the_uncategorised_ones_come_after_the_named_categories(
    client, create_user, create_listing, create_category, login_as
):
    me = await create_user()
    login_as(me)
    books = await create_category(category_name="Books")
    await create_listing(seller_id=me.id, status="active", category_id=None)
    await create_listing(seller_id=me.id, status="active", category_id=books.id)

    by_category = (await _stats(client))["selling"]["by_category"]

    assert [c["category_name"] for c in by_category] == ["Books", None]


async def test_buying_counts_what_i_bought_and_what_i_spent(
    client, create_user, create_listing, login_as
):
    me = await create_user()
    login_as(me)
    await create_listing(status="sold", buyer_id=me.id, price=40)
    await create_listing(status="sold", buyer_id=me.id, price=61)

    buying = (await _stats(client))["buying"]

    assert buying["count"] == 2
    assert buying["total_spent"] == 101
    assert buying["average_price"] == 50.5


async def test_buying_ignores_other_buyers_unsold_and_deleted_listings(
    client, create_user, create_listing, login_as
):
    me = await create_user()
    login_as(me)
    someone = await create_user()
    await create_listing(status="sold", buyer_id=someone.id, price=10)  # bought by someone else
    await create_listing(status="active", buyer_id=me.id, price=20)  # not sold
    await create_listing(status="sold", buyer_id=me.id, price=30, deleted_at=datetime.now(UTC))

    buying = (await _stats(client))["buying"]

    assert buying == {"count": 0, "total_spent": 0, "average_price": 0.0, "by_category": []}


async def test_buying_by_category_counts_and_sums_spent(
    client, create_user, create_listing, create_category, login_as
):
    me = await create_user()
    login_as(me)
    books = await create_category(category_name="Books")
    tech = await create_category(category_name="Tech")
    await create_listing(status="sold", buyer_id=me.id, price=10, category_id=books.id)
    await create_listing(status="sold", buyer_id=me.id, price=300, category_id=tech.id)
    await create_listing(status="sold", buyer_id=me.id, price=200, category_id=tech.id)

    by_category = (await _stats(client))["buying"]["by_category"]

    assert by_category == [
        {"category_id": tech.id, "category_name": "Tech", "count": 2, "total_spent": 500},
        {"category_id": books.id, "category_name": "Books", "count": 1, "total_spent": 10},
    ]


async def test_selling_and_buying_are_independent(
    client, create_user, create_listing, login_as
):
    me = await create_user()
    login_as(me)
    await create_listing(seller_id=me.id, status="sold", price=70)
    await create_listing(status="sold", buyer_id=me.id, price=25)

    stats = await _stats(client)

    assert stats["selling"]["sold"]["total_value"] == 70
    assert stats["buying"]["total_spent"] == 25
