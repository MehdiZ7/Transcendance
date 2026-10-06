import uuid
from datetime import UTC, datetime

from app.core.config import settings


async def test_list_listings_returns_only_active_listings(client, create_listing):
    await create_listing(title="Clavier mécanique", price=4500)
    await create_listing(title="Écran 27 pouces", price=15000, status="draft")

    response = await client.get("/api/v1/listings")

    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 1
    assert [item["title"] for item in body["data"]] == ["Clavier mécanique"]


async def test_list_listings_hides_listings_of_suspended_and_removed_sellers(
    client, create_user, create_listing
):
    suspended = await create_user(is_active=False)
    # still flagged active: deleted_at alone must hide the listings
    removed = await create_user(deleted_at=datetime.now(UTC))
    await create_listing(title="En ligne")
    await create_listing(title="Vendeur suspendu", seller_id=suspended.id)
    await create_listing(title="Vendeur retiré", seller_id=removed.id)

    response = await client.get("/api/v1/listings")

    body = response.json()
    assert [listing["title"] for listing in body["data"]] == ["En ligne"]
    assert body["total"] == 1


async def test_list_listings_shows_them_again_once_the_seller_is_reactivated(
    client, db_session, create_user, create_listing
):
    seller = await create_user(is_active=False)
    await create_listing(title="De retour", seller_id=seller.id)
    seller.is_active = True
    await db_session.flush()

    response = await client.get("/api/v1/listings")

    assert [listing["title"] for listing in response.json()["data"]] == ["De retour"]


async def test_list_listings_excludes_current_users_own_listings(
    client, create_user, create_listing, login_as
):
    me = await create_user()
    login_as(me)
    await create_listing(title="Ma propre annonce", seller_id=me.id)
    await create_listing(title="Annonce d'un autre")

    response = await client.get("/api/v1/listings")

    assert [item["title"] for item in response.json()["data"]] == ["Annonce d'un autre"]


async def test_list_listings_includes_own_listings_when_not_authenticated(
    client, create_user, create_listing
):
    seller = await create_user()
    await create_listing(title="Annonce", seller_id=seller.id)

    response = await client.get("/api/v1/listings")

    assert [item["title"] for item in response.json()["data"]] == ["Annonce"]


async def test_list_listings_returns_seller_category_and_location(
    client, create_user, create_category, create_location, create_listing
):
    seller = await create_user(display_name="Camille R.")
    category = await create_category(category_name="Objet")
    location = await create_location(location="42 Paris")
    await create_listing(
        title="Clavier mécanique",
        seller_id=seller.id,
        category_id=category.id,
        location_id=location.id,
    )

    response = await client.get("/api/v1/listings")

    body = response.json()["data"][0]
    assert body["seller"]["display_name"] == "Camille R."
    assert body["category"]["category_name"] == "Objet"
    assert body["location"]["location"] == "42 Paris"


async def test_list_listings_returns_null_category_and_location_when_unset(client, create_listing):
    await create_listing(title="No category listing")

    response = await client.get("/api/v1/listings")

    body = response.json()["data"][0]
    assert body["category"] is None
    assert body["location"] is None
    assert body["seller"] is not None


async def test_list_listings_returns_cover_image_storage_path(
    client, db_session, create_listing, create_listing_image
):
    listing = await create_listing(title="Clavier mécanique")
    image = await create_listing_image(listing_id=listing.id, storage_path="/mock/listings/a.jpg")
    listing.cover_image_id = image.id
    await db_session.flush()

    response = await client.get("/api/v1/listings")

    body = response.json()["data"][0]
    assert body["cover_image_id"] == "/mock/listings/a.jpg"


async def test_list_listings_returns_null_cover_image_when_no_images(client, create_listing):
    await create_listing(title="No image listing")

    response = await client.get("/api/v1/listings")

    assert response.json()["data"][0]["cover_image_id"] is None


async def test_list_listings_returns_favorites_count(
    client, create_listing, create_listing_favorite
):
    listing = await create_listing(title="Popular")
    await create_listing_favorite(listing_id=listing.id)
    await create_listing_favorite(listing_id=listing.id)

    response = await client.get("/api/v1/listings")

    assert response.json()["data"][0]["favorites_count"] == 2


async def test_list_listings_is_favorited_false_when_not_authenticated(
    client, create_listing, create_listing_favorite
):
    listing = await create_listing(title="Favorited by someone else")
    await create_listing_favorite(listing_id=listing.id)

    response = await client.get("/api/v1/listings")

    assert response.json()["data"][0]["is_favorited"] is False


async def test_list_listings_returns_is_favorited_for_current_user(
    client, create_user, create_listing, create_listing_favorite, login_as
):
    me = await create_user()
    login_as(me)
    favorited = await create_listing(title="Favorited by me")
    await create_listing_favorite(listing_id=favorited.id, user_id=me.id)
    await create_listing(title="Not favorited")

    response = await client.get("/api/v1/listings", params={"sort": "recent"})

    by_title = {item["title"]: item["is_favorited"] for item in response.json()["data"]}
    assert by_title["Favorited by me"] is True
    assert by_title["Not favorited"] is False


async def test_list_listings_sorts_by_price_asc(client, create_listing):
    await create_listing(title="Expensive", price=9000)
    await create_listing(title="Cheap", price=100)

    response = await client.get("/api/v1/listings", params={"sort": "price_asc"})

    titles = [item["title"] for item in response.json()["data"]]
    assert titles == ["Cheap", "Expensive"]


async def test_list_listings_paginates(client, create_listing):
    for i in range(3):
        await create_listing(title=f"Listing {i}")

    response = await client.get("/api/v1/listings", params={"limit": 2, "page": 2})
    body = response.json()

    assert body["total"] == 3
    assert body["total_pages"] == 2
    assert len(body["data"]) == 1


async def test_list_listings_filters_by_categorie_and_prix(client, create_listing, create_category):
    category_a = await create_category()
    category_b = await create_category()
    await create_listing(title="In range", price=500, category_id=category_a.id)
    await create_listing(title="Too expensive", price=5000, category_id=category_a.id)
    await create_listing(title="Wrong category", price=500, category_id=category_b.id)

    response = await client.get(
        "/api/v1/listings", params={"categorie": category_a.id, "prix_min": 100, "prix_max": 1000}
    )

    titles = [item["title"] for item in response.json()["data"]]
    assert titles == ["In range"]


async def test_list_listings_searches_by_q(client, create_listing):
    await create_listing(title="Clavier mécanique Keychron")
    await create_listing(title="Écran Dell")

    response = await client.get("/api/v1/listings", params={"q": "clavier"})

    titles = [item["title"] for item in response.json()["data"]]
    assert titles == ["Clavier mécanique Keychron"]


async def test_get_listing_returns_detail_with_relations(client, create_listing):
    listing = await create_listing(title="Clavier mécanique", price=6500)

    response = await client.get(f"/api/v1/listings/{listing.public_id}")

    assert response.status_code == 200
    body = response.json()
    assert body["title"] == "Clavier mécanique"
    assert body["seller"]["display_name"] == "Test User"
    assert body["favorites_count"] == 0
    assert body["is_favorited"] is False


async def test_get_listing_returns_is_favorited_true_for_current_user(
    client, create_user, create_listing, create_listing_favorite, login_as
):
    listing = await create_listing()
    me = await create_user()
    login_as(me)
    await create_listing_favorite(listing_id=listing.id, user_id=me.id)

    response = await client.get(f"/api/v1/listings/{listing.public_id}")

    assert response.json()["is_favorited"] is True


async def test_get_listing_returns_404_for_unknown_public_id(client):
    response = await client.get("/api/v1/listings/00000000-0000-0000-0000-000000000000")

    assert response.status_code == 404


async def test_create_listing_requires_authentication(client, create_category, create_location):
    category = await create_category()
    location = await create_location()

    response = await client.post(
        "/api/v1/listings",
        json={
            "title": "Test",
            "body": "Test",
            "price": 100,
            "category_id": category.id,
            "location_id": location.id,
        },
    )

    assert response.status_code == 401


async def test_create_listing_persists_and_returns_detail(
    client, create_user, create_category, create_location, login_as
):
    seller = await create_user()
    login_as(seller)
    category = await create_category()
    location = await create_location()

    response = await client.post(
        "/api/v1/listings",
        json={
            "title": "Clavier mécanique",
            "body": "TKL, switches brown",
            "price": 6500,
            "category_id": category.id,
            "location_id": location.id,
            "condition": "like_new",
            "image_urls": ["https://cdn.intra.42.fr/a.jpg", "https://cdn.intra.42.fr/b.jpg"],
        },
    )

    assert response.status_code == 201
    body = response.json()
    assert body["title"] == "Clavier mécanique"
    assert body["status"] == "active"
    assert body["seller"]["public_id"] == str(seller.public_id)
    assert body["category"]["id"] == category.id
    assert [img["storage_path"] for img in body["images"]] == [
        "https://cdn.intra.42.fr/a.jpg",
        "https://cdn.intra.42.fr/b.jpg",
    ]
    assert body["cover_image_id"] == "https://cdn.intra.42.fr/a.jpg"

    listing_response = await client.get(f"/api/v1/listings/{body['public_id']}")
    assert listing_response.status_code == 200


async def test_create_listing_uses_current_user_as_seller(
    client, create_user, create_category, create_location, login_as
):
    me = await create_user()
    login_as(me)
    category = await create_category()
    location = await create_location()

    response = await client.post(
        "/api/v1/listings",
        json={
            "title": "Clavier mécanique",
            "body": "TKL, switches brown",
            "price": 6500,
            "category_id": category.id,
            "location_id": location.id,
        },
    )

    assert response.status_code == 201
    assert response.json()["seller"]["public_id"] == str(me.public_id)


async def test_create_listing_returns_404_for_unknown_category(
    client, create_user, create_location, login_as
):
    login_as(await create_user())
    location = await create_location()

    response = await client.post(
        "/api/v1/listings",
        json={
            "title": "Test",
            "body": "Test",
            "price": 100,
            "category_id": 999999,
            "location_id": location.id,
        },
    )

    assert response.status_code == 404


async def test_create_listing_returns_404_for_unknown_location(
    client, create_user, create_category, login_as
):
    login_as(await create_user())
    category = await create_category()

    response = await client.post(
        "/api/v1/listings",
        json={
            "title": "Test",
            "body": "Test",
            "price": 100,
            "category_id": category.id,
            "location_id": 999999,
        },
    )

    assert response.status_code == 404


async def test_delete_listing_requires_authentication(client, create_listing):
    listing = await create_listing()

    response = await client.delete(f"/api/v1/listings/{listing.public_id}")

    assert response.status_code == 401


async def test_delete_listing_soft_deletes_own_listing(
    client, db_session, create_user, create_listing, login_as
):
    me = await create_user()
    login_as(me)
    listing = await create_listing(seller_id=me.id)

    response = await client.delete(f"/api/v1/listings/{listing.public_id}")

    assert response.status_code == 204
    assert response.content == b""
    await db_session.refresh(listing)
    assert listing.status == "deleted"
    assert listing.deleted_at is not None

    follow_up = await client.get(f"/api/v1/listings/{listing.public_id}")
    assert follow_up.status_code == 404


async def test_delete_listing_returns_403_for_non_seller(
    client, db_session, create_user, create_listing, login_as
):
    login_as(await create_user())
    listing = await create_listing()

    response = await client.delete(f"/api/v1/listings/{listing.public_id}")

    assert response.status_code == 403
    await db_session.refresh(listing)
    assert listing.status == "active"
    assert listing.deleted_at is None


async def test_delete_listing_returns_409_when_sold(
    client, db_session, create_user, create_listing, login_as
):
    # The buyer can only review while the listing is SOLD
    # deleting it would let the seller dodge the review
    me = await create_user()
    login_as(me)
    listing = await create_listing(seller_id=me.id, status="sold")

    response = await client.delete(f"/api/v1/listings/{listing.public_id}")

    assert response.status_code == 409
    await db_session.refresh(listing)
    assert listing.status == "sold"


async def test_delete_listing_returns_404_when_already_deleted(
    client, create_user, create_listing, login_as
):
    me = await create_user()
    login_as(me)
    listing = await create_listing(seller_id=me.id, status="deleted")

    response = await client.delete(f"/api/v1/listings/{listing.public_id}")

    assert response.status_code == 404


async def test_delete_listing_returns_404_for_unknown_listing(client, create_user, login_as):
    login_as(await create_user())

    response = await client.delete(f"/api/v1/listings/{uuid.uuid4()}")

    assert response.status_code == 404


async def test_delete_listing_removes_its_uploaded_images(
    client, create_user, create_listing, create_listing_image, login_as, tmp_path, monkeypatch
):
    monkeypatch.setattr(settings, "media_root", str(tmp_path))
    me = await create_user()
    login_as(me)
    listing = await create_listing(seller_id=me.id)
    directory = tmp_path / "images" / str(me.public_id)
    directory.mkdir(parents=True)
    file_path = directory / ("a" * 32 + ".png")
    file_path.write_bytes(b"fake")
    await create_listing_image(
        listing_id=listing.id, storage_path=f"/media/images/{me.public_id}/{'a' * 32}.png"
    )

    response = await client.delete(f"/api/v1/listings/{listing.public_id}")

    assert response.status_code == 204
    assert not file_path.exists()


async def test_delete_listing_ignores_images_that_are_not_uploads(
    client, create_user, create_listing, create_listing_image, login_as
):
    me = await create_user()
    login_as(me)
    listing = await create_listing(seller_id=me.id)
    await create_listing_image(listing_id=listing.id, storage_path="/mock/listings/default.jpg")

    response = await client.delete(f"/api/v1/listings/{listing.public_id}")

    assert response.status_code == 204

async def test_mark_listing_sold_requires_authentication(client, create_listing):
    listing = await create_listing()

    response = await client.post(f"/api/v1/listings/{listing.public_id}/mark-sold")

    assert response.status_code == 401


async def test_mark_listing_sold(client, db_session, create_user, create_listing, login_as):
    me = await create_user()
    login_as(me)
    listing = await create_listing(seller_id=me.id, status="active")

    response = await client.post(f"/api/v1/listings/{listing.public_id}/mark-sold")

    assert response.status_code == 204
    await db_session.refresh(listing)
    assert listing.status == "sold"
    assert listing.buyer_id is None


async def test_mark_listing_sold_returns_403_when_not_seller(
    client, db_session, create_user, create_listing, login_as
):
    login_as(await create_user())
    listing = await create_listing(status="active")

    response = await client.post(f"/api/v1/listings/{listing.public_id}/mark-sold")

    assert response.status_code == 403
    await db_session.refresh(listing)
    assert listing.status == "active"


async def test_mark_listing_sold_returns_409_when_not_active(
    client, create_user, create_listing, login_as
):
    me = await create_user()
    login_as(me)
    listing = await create_listing(seller_id=me.id, status="sold")

    response = await client.post(f"/api/v1/listings/{listing.public_id}/mark-sold")

    assert response.status_code == 409


async def test_mark_listing_sold_returns_404_when_deleted(
    client, create_user, create_listing, login_as
):
    me = await create_user()
    login_as(me)
    listing = await create_listing(seller_id=me.id, status="deleted")

    response = await client.post(f"/api/v1/listings/{listing.public_id}/mark-sold")

    assert response.status_code == 404


async def test_add_favorite_requires_authentication(client, create_listing):
    listing = await create_listing()

    response = await client.post(f"/api/v1/listings/{listing.public_id}/favorite")

    assert response.status_code == 401


async def test_add_favorite_marks_listing_favorited(
    client, create_user, create_listing, login_as
):
    me = await create_user()
    login_as(me)
    listing = await create_listing()

    response = await client.post(f"/api/v1/listings/{listing.public_id}/favorite")

    assert response.status_code == 200
    assert response.json() == {
        "is_favorited": True,
        "favorites_count": 1,
        "message": None,
    }


async def test_add_favorite_is_idempotent(client, create_user, create_listing, login_as):
    me = await create_user()
    login_as(me)
    listing = await create_listing()

    await client.post(f"/api/v1/listings/{listing.public_id}/favorite")
    response = await client.post(f"/api/v1/listings/{listing.public_id}/favorite")

    assert response.status_code == 200
    assert response.json()["favorites_count"] == 1


async def test_add_favorite_returns_404_for_unknown_listing(client, create_user, login_as):
    login_as(await create_user())

    response = await client.post(
        f"/api/v1/listings/{uuid.uuid4()}/favorite"
    )

    assert response.status_code == 404


async def test_add_favorite_counts_across_different_users(
    client, create_user, create_listing, create_listing_favorite, login_as
):
    me = await create_user()
    login_as(me)
    listing = await create_listing()
    await create_listing_favorite(listing_id=listing.id, user_id=(await create_user()).id)

    response = await client.post(f"/api/v1/listings/{listing.public_id}/favorite")

    assert response.status_code == 200
    assert response.json() == {
        "is_favorited": True,
        "favorites_count": 2,
        "message": None,
    }


async def test_remove_favorite_requires_authentication(client, create_listing):
    listing = await create_listing()

    response = await client.delete(f"/api/v1/listings/{listing.public_id}/favorite")

    assert response.status_code == 401


async def test_remove_favorite_unmarks_listing_favorited(
    client, create_user, create_listing, create_listing_favorite, login_as
):
    me = await create_user()
    login_as(me)
    listing = await create_listing()
    await create_listing_favorite(listing_id=listing.id, user_id=me.id)

    response = await client.delete(f"/api/v1/listings/{listing.public_id}/favorite")

    assert response.status_code == 200
    assert response.json() == {
        "is_favorited": False,
        "favorites_count": 0,
        "message": None,
    }


async def test_remove_favorite_is_idempotent_when_not_favorited(
    client, create_user, create_listing, login_as
):
    me = await create_user()
    login_as(me)
    listing = await create_listing()

    response = await client.delete(f"/api/v1/listings/{listing.public_id}/favorite")

    assert response.status_code == 200
    assert response.json()["favorites_count"] == 0


async def test_remove_favorite_only_removes_current_users_favorite(
    client, create_user, create_listing, create_listing_favorite, login_as
):
    me = await create_user()
    other = await create_user()
    login_as(me)
    listing = await create_listing()
    await create_listing_favorite(listing_id=listing.id, user_id=other.id)

    response = await client.delete(f"/api/v1/listings/{listing.public_id}/favorite")

    assert response.status_code == 200
    assert response.json()["favorites_count"] == 1


async def test_remove_favorite_returns_404_for_unknown_listing(client, create_user, login_as):
    login_as(await create_user())

    response = await client.delete(f"/api/v1/listings/{uuid.uuid4()}/favorite")

    assert response.status_code == 404
