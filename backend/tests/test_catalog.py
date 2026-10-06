from app.models import CategoryAttribute


async def test_list_categories_returns_all_with_attributes(client, create_category, db_session):
    category = await create_category(category_name="Objet")
    db_session.add(
        CategoryAttribute(category_id=category.id, key="brand", data_type="text", is_filterable=True)
    )
    await db_session.flush()

    response = await client.get("/api/v1/categories")

    assert response.status_code == 200
    body = response.json()
    assert len(body) == 1
    assert body[0]["category_name"] == "Objet"
    assert body[0]["attributes"] == [
        {
            "id": body[0]["attributes"][0]["id"],
            "key": "brand",
            "data_type": "text",
            "unit": None,
            "is_required": False,
            "is_filterable": True,
            "options": None,
        }
    ]


async def test_list_categories_returns_empty_attributes_when_none_defined(client, create_category):
    await create_category(category_name="Cours")

    response = await client.get("/api/v1/categories")

    body = response.json()
    assert body[0]["attributes"] == []


async def test_list_locations_returns_all(client, create_location):
    await create_location(location="42 Paris")
    await create_location(location="42 Lyon")

    response = await client.get("/api/v1/locations")

    assert response.status_code == 200
    names = sorted(item["location"] for item in response.json())
    assert names == ["42 Lyon", "42 Paris"]
