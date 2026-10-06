from datetime import UTC, date, datetime, timedelta
from zoneinfo import ZoneInfo

import pytest
import pytest_asyncio

from app.core import presence
from app.models import Report

PARIS = ZoneInfo("Europe/Paris")

PATHS = [
    "/api/v1/analytics",
    "/api/v1/analytics/online-students",
    "/api/v1/analytics/listings-today",
    "/api/v1/analytics/pending-reports",
    "/api/v1/analytics/sold-percentage",
    "/api/v1/analytics/category-distribution",
    "/api/v1/analytics/listings-between-dates",
    "/api/v1/analytics/total-value",
    "/api/v1/analytics/average-price",
    "/api/v1/analytics/messages-count",
    "/api/v1/analytics/top-liked",
]


@pytest_asyncio.fixture(autouse=True)
def clear_presence():
    """The online registry is module-level state that survives between tests -
    wipe it so one test's logins don't inflate the next one's count."""
    presence.reset()
    yield
    presence.reset()


@pytest_asyncio.fixture
def create_report(db_session, create_user):
    async def _create(**kwargs) -> Report:
        if "reporter_id" not in kwargs:
            reporter = await create_user()
            kwargs["reporter_id"] = reporter.id
        defaults = {
            "target_type": "listing",
            "target_id": 1,
            "reason": "Contenu inapproprié",
            "status": "open",
        }
        defaults.update(kwargs)
        report = Report(**defaults)
        db_session.add(report)
        await db_session.flush()
        return report

    return _create


async def _admin(client, create_user, login_as):
    admin = await create_user(role="admin")
    login_as(admin)
    return admin


def _paris_noon(day: date) -> datetime:
    return datetime(day.year, day.month, day.day, 12, tzinfo=PARIS)


@pytest.mark.parametrize("path", PATHS)
async def test_analytics_returns_401_when_anonymous(client, path):
    assert (await client.get(path)).status_code == 401


@pytest.mark.parametrize("path", PATHS)
async def test_analytics_returns_403_for_non_admin(client, create_user, login_as, path):
    login_as(await create_user(role="user"))
    assert (await client.get(path)).status_code == 403


@pytest.mark.parametrize("path", PATHS)
async def test_analytics_returns_200_for_admin(client, create_user, login_as, path):
    login_as(await create_user(role="admin"))
    assert (await client.get(path)).status_code == 200


# online-students


async def test_online_students_counts_users_seen_recently(
    client, create_user, create_location, login_as
):
    campus = await create_location(location="42 Paris")
    visitors = [
        await create_user(location_id=campus.id),
        await create_user(location_id=campus.id),
        await create_user(),
    ]
    for visitor in visitors:
        login_as(visitor)
        assert (await client.get("/api/v1/users/me")).status_code == 200
    await _admin(client, create_user, login_as)

    response = await client.get("/api/v1/analytics/online-students")

    assert response.status_code == 200
    body = response.json()
    # three visitors plus the admin reading the dashboard
    assert body["total"] == 4
    assert sum(item["count"] for item in body["byCampus"]) == 2


async def test_online_students_groups_by_campus(
    client, create_user, create_location, login_as
):
    campus_a = await create_location(location="Campus A")
    campus_b = await create_location(location="Campus B")
    for location_id in (campus_a.id, campus_a.id, campus_b.id):
        user = await create_user(location_id=location_id)
        presence.touch(user.id)
    await _admin(client, create_user, login_as)

    response = await client.get("/api/v1/analytics/online-students")

    assert response.json()["byCampus"] == [
        {"campusId": str(campus_a.id), "campusName": "Campus A", "count": 2},
        {"campusId": str(campus_b.id), "campusName": "Campus B", "count": 1},
    ]


async def test_online_students_returns_zero_when_nobody_seen(
    client, create_user, login_as
):
    await _admin(client, create_user, login_as)

    response = await client.get("/api/v1/analytics/online-students")

    body = response.json()
    assert body["total"] == 1
    assert body["byCampus"] == []
    assert body["peakToday"] == 1


async def test_online_students_peak_today_keeps_the_high_water_mark(
    client, create_user, login_as, monkeypatch
):
    for _ in range(2):
        presence.touch((await create_user()).id)
    await _admin(client, create_user, login_as)

    first = (await client.get("/api/v1/analytics/online-students")).json()
    monkeypatch.setattr(presence, "ONLINE_WINDOW", timedelta(seconds=-1))
    second = (await client.get("/api/v1/analytics/online-students")).json()

    assert first["total"] == 3
    assert first["peakToday"] == 3
    assert second["total"] == 0
    assert second["peakToday"] == 3


async def test_online_students_response_uses_camel_case_keys(
    client, create_user, login_as
):
    await _admin(client, create_user, login_as)

    body = (await client.get("/api/v1/analytics/online-students")).json()

    assert "byCampus" in body
    assert "peakToday" in body
    assert "updatedAt" in body
    assert "by_campus" not in body


# listings-today


async def test_listings_today_counts_only_todays_listings(
    client, create_user, create_listing, login_as
):
    await create_listing()
    await create_listing()
    await create_listing(created_at=datetime.now(UTC) - timedelta(days=1))
    await _admin(client, create_user, login_as)

    response = await client.get("/api/v1/analytics/listings-today")

    body = response.json()
    assert body["count"] == 2
    assert body["comparedToYesterdayPercent"] == 100.0
    assert body["date"] == datetime.now(PARIS).date().isoformat()


async def test_listings_today_excludes_drafts_and_deleted(
    client, create_user, create_listing, login_as
):
    await create_listing()
    await create_listing(status="draft")
    await create_listing(deleted_at=datetime.now(UTC))
    await _admin(client, create_user, login_as)

    response = await client.get("/api/v1/analytics/listings-today")

    assert response.json()["count"] == 1


async def test_listings_today_by_category_includes_empty_categories(
    client, create_user, create_category, create_listing, login_as
):
    full = await create_category(category_name="Informatique")
    empty = await create_category(category_name="Livres")
    await create_listing(category_id=full.id)
    await _admin(client, create_user, login_as)

    response = await client.get("/api/v1/analytics/listings-today")

    assert response.json()["byCategory"] == [
        {"categoryId": str(full.id), "categoryName": "Informatique", "count": 1},
        {"categoryId": str(empty.id), "categoryName": "Livres", "count": 0},
    ]


async def test_listings_today_percent_is_100_when_yesterday_was_empty(
    client, create_user, create_listing, login_as
):
    await create_listing()
    await _admin(client, create_user, login_as)

    response = await client.get("/api/v1/analytics/listings-today")

    assert response.json()["comparedToYesterdayPercent"] == 100.0


async def test_listings_today_percent_is_0_when_both_days_empty(
    client, create_user, login_as
):
    await _admin(client, create_user, login_as)

    response = await client.get("/api/v1/analytics/listings-today")

    body = response.json()
    assert body["count"] == 0
    assert body["comparedToYesterdayPercent"] == 0.0


# pending-reports


async def test_pending_reports_counts_only_open_reports(
    client, create_user, create_report, login_as
):
    await create_report()
    await create_report()
    await create_report(status="resolved")
    await create_report(status="in_progress")
    await _admin(client, create_user, login_as)

    response = await client.get("/api/v1/analytics/pending-reports")

    assert response.json()["count"] == 2


async def test_pending_reports_groups_by_target_type(
    client, create_user, create_report, login_as
):
    for target_type in ("listing", "message", "user", "review"):
        await create_report(target_type=target_type)
    await _admin(client, create_user, login_as)

    response = await client.get("/api/v1/analytics/pending-reports")

    body = response.json()
    assert body["count"] == 4
    assert body["byTargetType"] == {"listing": 1, "message": 1, "user": 1, "review": 1}


async def test_pending_reports_target_types_default_to_zero(
    client, create_user, login_as
):
    await _admin(client, create_user, login_as)

    response = await client.get("/api/v1/analytics/pending-reports")

    body = response.json()
    assert body["count"] == 0
    assert body["byTargetType"] == {"listing": 0, "message": 0, "user": 0, "review": 0}


async def test_pending_reports_flags_urgent_reasons(
    client, create_user, create_report, login_as
):
    await create_report(reason="Arnaque évidente")
    await create_report(reason="profil suspect")
    await create_report(reason="Objet cassé")
    await create_report(reason="ARNAQUE mais déjà traitée", status="resolved")
    await _admin(client, create_user, login_as)

    response = await client.get("/api/v1/analytics/pending-reports")

    assert response.json()["urgentCount"] == 2


async def test_pending_reports_oldest_date_is_the_earliest_open_report(
    client, create_user, create_report, login_as
):
    oldest = datetime(2026, 1, 5, 9, 30, tzinfo=UTC)
    await create_report(created_at=datetime(2026, 1, 10, tzinfo=UTC))
    await create_report(created_at=oldest)
    await create_report(created_at=datetime(2025, 12, 1, tzinfo=UTC), status="resolved")
    await _admin(client, create_user, login_as)

    response = await client.get("/api/v1/analytics/pending-reports")

    assert datetime.fromisoformat(response.json()["oldestReportDate"]) == oldest


async def test_pending_reports_oldest_date_is_null_when_none_open(
    client, create_user, create_report, login_as
):
    await create_report(status="closed")
    await _admin(client, create_user, login_as)

    response = await client.get("/api/v1/analytics/pending-reports")

    assert response.json()["oldestReportDate"] is None


# sold-percentage


async def test_sold_percentage_computes_ratio(
    client, create_user, create_listing, login_as
):
    await create_listing(status="sold")
    for _ in range(3):
        await create_listing()
    await _admin(client, create_user, login_as)

    response = await client.get("/api/v1/analytics/sold-percentage")

    body = response.json()
    assert body["soldCount"] == 1
    assert body["activeCount"] == 3
    assert body["totalCount"] == 4
    assert body["percentage"] == 25.0


async def test_sold_percentage_excludes_drafts_and_expired(
    client, create_user, create_listing, login_as
):
    await create_listing(status="sold")
    await create_listing()
    await create_listing(status="draft")
    await create_listing(status="expired")
    await create_listing(status="archived")
    await create_listing(status="sold", deleted_at=datetime.now(UTC))
    await _admin(client, create_user, login_as)

    response = await client.get("/api/v1/analytics/sold-percentage")

    body = response.json()
    assert body["soldCount"] == 1
    assert body["activeCount"] == 1
    assert body["totalCount"] == 2
    assert body["percentage"] == 50.0


async def test_sold_percentage_is_zero_when_no_listings(client, create_user, login_as):
    await _admin(client, create_user, login_as)

    response = await client.get("/api/v1/analytics/sold-percentage")

    assert response.status_code == 200
    body = response.json()
    assert body["totalCount"] == 0
    assert body["percentage"] == 0.0
    assert body["averageTimeToSellDays"] == 0.0


async def test_sold_percentage_average_time_uses_updated_at(
    client, create_user, create_listing, login_as
):
    now = datetime.now(UTC)
    await create_listing(
        status="sold", created_at=now - timedelta(days=4), updated_at=now
    )
    await _admin(client, create_user, login_as)

    response = await client.get("/api/v1/analytics/sold-percentage")

    assert response.json()["averageTimeToSellDays"] == 4.0


#  category-distribution


async def test_category_distribution_percentages_sum_to_100(
    client, create_user, create_category, create_listing, login_as
):
    small = await create_category(category_name="Livres")
    big = await create_category(category_name="Informatique")
    await create_listing(category_id=small.id)
    for _ in range(3):
        await create_listing(category_id=big.id)
    await _admin(client, create_user, login_as)

    response = await client.get("/api/v1/analytics/category-distribution")

    body = response.json()
    assert body["totalListings"] == 4
    by_name = {item["categoryName"]: item for item in body["categories"]}
    assert by_name["Informatique"]["count"] == 3
    assert by_name["Informatique"]["percentage"] == 75.0
    assert by_name["Livres"]["count"] == 1
    assert by_name["Livres"]["percentage"] == 25.0


async def test_category_distribution_omits_color(
    client, create_user, create_category, create_listing, login_as
):
    category = await create_category()
    await create_listing(category_id=category.id)
    await _admin(client, create_user, login_as)

    response = await client.get("/api/v1/analytics/category-distribution")

    assert "color" not in response.json()["categories"][0]


async def test_category_distribution_is_empty_when_no_listings(
    client, create_user, create_category, login_as
):
    await create_category(category_name="Livres")
    await create_category(category_name="Informatique")
    await _admin(client, create_user, login_as)

    response = await client.get("/api/v1/analytics/category-distribution")

    assert response.status_code == 200
    body = response.json()
    assert body["totalListings"] == 0
    assert len(body["categories"]) == 2
    assert all(item["count"] == 0 for item in body["categories"])
    assert all(item["percentage"] == 0.0 for item in body["categories"])


#  listings-between-dates


async def test_listings_between_dates_defaults_to_last_30_days(
    client, create_user, login_as
):
    await _admin(client, create_user, login_as)

    response = await client.get("/api/v1/analytics/listings-between-dates")

    body = response.json()
    today = datetime.now(PARIS).date()
    assert body["endDate"] == today.isoformat()
    assert body["startDate"] == (today - timedelta(days=30)).isoformat()
    assert len(body["dailyBreakdown"]) == 31


async def test_listings_between_dates_zero_fills_gap_days(
    client, create_user, create_listing, login_as
):
    await create_listing(created_at=_paris_noon(date(2026, 1, 10)))
    await create_listing(created_at=_paris_noon(date(2026, 1, 12)))
    await create_listing(created_at=_paris_noon(date(2026, 1, 13)))
    await _admin(client, create_user, login_as)

    response = await client.get(
        "/api/v1/analytics/listings-between-dates",
        params={"startDate": "2026-01-10", "endDate": "2026-01-12"},
    )

    body = response.json()
    assert body["dailyBreakdown"] == [
        {"date": "2026-01-10", "count": 1},
        {"date": "2026-01-11", "count": 0},
        {"date": "2026-01-12", "count": 1},
    ]
    assert body["totalCount"] == 2


async def test_listings_between_dates_swaps_reversed_range(
    client, create_user, login_as
):
    await _admin(client, create_user, login_as)

    response = await client.get(
        "/api/v1/analytics/listings-between-dates",
        params={"startDate": "2026-01-12", "endDate": "2026-01-10"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["startDate"] == "2026-01-10"
    assert body["endDate"] == "2026-01-12"
    assert len(body["dailyBreakdown"]) == 3


async def test_listings_between_dates_rejects_range_over_one_year(
    client, create_user, login_as
):
    await _admin(client, create_user, login_as)

    response = await client.get(
        "/api/v1/analytics/listings-between-dates",
        params={"startDate": "2025-01-01", "endDate": "2026-01-10"},
    )

    assert response.status_code == 422


async def test_listings_between_dates_rejects_malformed_date(
    client, create_user, login_as
):
    await _admin(client, create_user, login_as)

    response = await client.get(
        "/api/v1/analytics/listings-between-dates", params={"startDate": "not-a-date"}
    )

    assert response.status_code == 422


@pytest.mark.parametrize(
    ("start", "end", "field"),
    [
        ("9999-12-31", "9999-12-31", "startDate"),  # used to overflow: OverflowError, 500
        ("0001-01-01", "0001-01-02", "startDate"),  # used to reach year 0 in UTC: 500
        ("1999-12-31", "2000-01-05", "startDate"),
        ("2100-12-30", "2101-01-01", "endDate"),
    ],
)
async def test_listings_between_dates_rejects_dates_outside_the_supported_years(
    client, create_user, login_as, start, end, field
):
    await _admin(client, create_user, login_as)

    response = await client.get(
        "/api/v1/analytics/listings-between-dates", params={"startDate": start, "endDate": end}
    )

    assert response.status_code == 422
    assert response.json()["detail"][0]["loc"][-1] == field


async def test_listings_between_dates_rejects_an_end_date_alone_far_in_the_past(
    client, create_user, login_as
):
    # startDate defaults to 30 days before endDate: that subtraction overflowed too
    await _admin(client, create_user, login_as)

    response = await client.get(
        "/api/v1/analytics/listings-between-dates", params={"endDate": "0001-01-10"}
    )

    assert response.status_code == 422


@pytest.mark.parametrize(("start", "end"), [("2000-01-01", "2000-01-02"), ("2100-12-30", "2100-12-31")])
async def test_listings_between_dates_accepts_the_edge_years(client, create_user, login_as, start, end):
    await _admin(client, create_user, login_as)

    response = await client.get(
        "/api/v1/analytics/listings-between-dates", params={"startDate": start, "endDate": end}
    )

    assert response.status_code == 200


async def test_dashboard_rejects_dates_outside_the_supported_years(client, create_user, login_as):
    await _admin(client, create_user, login_as)

    response = await client.get(
        "/api/v1/analytics", params={"startDate": "9999-12-31", "endDate": "9999-12-31"}
    )

    assert response.status_code == 422


async def test_listings_between_dates_accepts_camel_case_params(
    client, create_user, login_as
):
    await _admin(client, create_user, login_as)

    camel = await client.get(
        "/api/v1/analytics/listings-between-dates",
        params={"startDate": "2026-01-10", "endDate": "2026-01-12"},
    )
    snake = await client.get(
        "/api/v1/analytics/listings-between-dates",
        params={"start_date": "2026-01-10", "end_date": "2026-01-12"},
    )

    assert camel.json()["startDate"] == "2026-01-10"
    assert camel.json()["endDate"] == "2026-01-12"
    # snake_case is not bound, so the range falls back to the default
    assert snake.json()["endDate"] == datetime.now(PARIS).date().isoformat()


# total-value


async def test_total_value_sums_active_and_sold(
    client, create_user, create_listing, login_as
):
    await create_listing(price=100)
    await create_listing(price=200)
    await create_listing(price=50, status="sold")
    await _admin(client, create_user, login_as)

    response = await client.get("/api/v1/analytics/total-value")

    body = response.json()
    assert body["activeValue"] == 300
    assert body["soldValue"] == 50
    assert body["totalValue"] == 350


async def test_total_value_excludes_drafts_and_deleted(
    client, create_user, create_listing, login_as
):
    await create_listing(price=100)
    await create_listing(price=1000, status="draft")
    await create_listing(price=1000, deleted_at=datetime.now(UTC))
    await _admin(client, create_user, login_as)

    response = await client.get("/api/v1/analytics/total-value")

    body = response.json()
    assert body["activeValue"] == 100
    assert body["totalValue"] == 100


async def test_total_value_by_category_sums_per_category(
    client, create_user, create_category, create_listing, login_as
):
    tech = await create_category(category_name="Informatique")
    books = await create_category(category_name="Livres")
    empty = await create_category(category_name="Vêtements")
    await create_listing(price=100, category_id=tech.id)
    await create_listing(price=50, status="sold", category_id=tech.id)
    await create_listing(price=30, category_id=books.id)
    await _admin(client, create_user, login_as)

    response = await client.get("/api/v1/analytics/total-value")

    assert response.json()["byCategory"] == [
        {"categoryId": str(tech.id), "categoryName": "Informatique", "totalValue": 150},
        {"categoryId": str(books.id), "categoryName": "Livres", "totalValue": 30},
        {"categoryId": str(empty.id), "categoryName": "Vêtements", "totalValue": 0},
    ]


async def test_total_value_is_zero_on_empty_database(client, create_user, login_as):
    await _admin(client, create_user, login_as)

    response = await client.get("/api/v1/analytics/total-value")

    body = response.json()
    assert body["totalValue"] == 0
    assert body["activeValue"] == 0
    assert body["soldValue"] == 0
    assert body["currency"] == "EUR"


# average-price


async def test_average_price_computes_mean_median_and_bounds(
    client, create_user, create_listing, login_as
):
    for price in (100, 200, 300):
        await create_listing(price=price)
    await _admin(client, create_user, login_as)

    response = await client.get("/api/v1/analytics/average-price")

    body = response.json()
    assert body["averagePrice"] == 200.0
    assert body["medianPrice"] == 200.0
    assert body["minPrice"] == 100
    assert body["maxPrice"] == 300
    assert body["currency"] == "EUR"


async def test_average_price_median_on_even_count(
    client, create_user, create_listing, login_as
):
    await create_listing(price=100)
    await create_listing(price=200)
    await _admin(client, create_user, login_as)

    response = await client.get("/api/v1/analytics/average-price")

    # percentile_cont interpolates; percentile_disc would give 100
    assert response.json()["medianPrice"] == 150.0


async def test_average_price_excludes_free_listings(
    client, create_user, create_listing, login_as
):
    await create_listing(price=100)
    await create_listing(price=300)
    await create_listing(price=0)
    await _admin(client, create_user, login_as)

    response = await client.get("/api/v1/analytics/average-price")

    body = response.json()
    assert body["averagePrice"] == 200.0
    assert body["medianPrice"] == 200.0
    assert body["minPrice"] == 100


async def test_average_price_is_zero_on_empty_database(client, create_user, login_as):
    await _admin(client, create_user, login_as)

    response = await client.get("/api/v1/analytics/average-price")

    assert response.status_code == 200
    body = response.json()
    assert body["averagePrice"] == 0.0
    assert body["medianPrice"] == 0.0
    assert body["minPrice"] == 0
    assert body["maxPrice"] == 0


async def test_average_price_by_category_averages_per_category(
    client, create_user, create_category, create_listing, login_as
):
    tech = await create_category(category_name="Informatique")
    books = await create_category(category_name="Livres")
    await create_listing(price=100, category_id=tech.id)
    await create_listing(price=201, category_id=tech.id)
    await create_listing(price=20, category_id=books.id)
    await _admin(client, create_user, login_as)

    response = await client.get("/api/v1/analytics/average-price")

    assert response.json()["byCategory"] == [
        {
            "categoryId": str(tech.id),
            "categoryName": "Informatique",
            "averagePrice": 150.5,
        },
        {"categoryId": str(books.id), "categoryName": "Livres", "averagePrice": 20.0},
    ]


# messages-count


async def test_messages_count_totals_non_deleted_messages(
    client, create_user, create_conversation, create_message, login_as
):
    conversation = await create_conversation()
    await create_message(conversation_id=conversation.id)
    await create_message(conversation_id=conversation.id)
    await create_message(conversation_id=conversation.id, deleted_at=datetime.now(UTC))
    await _admin(client, create_user, login_as)

    response = await client.get("/api/v1/analytics/messages-count")

    assert response.json()["totalMessages"] == 2


async def test_messages_count_counts_todays_messages(
    client, create_user, create_conversation, create_message, login_as
):
    conversation = await create_conversation()
    await create_message(conversation_id=conversation.id)
    await create_message(
        conversation_id=conversation.id,
        created_at=datetime.now(UTC) - timedelta(days=1),
    )
    await _admin(client, create_user, login_as)

    response = await client.get("/api/v1/analytics/messages-count")

    body = response.json()
    assert body["messagesToday"] == 1
    assert body["totalMessages"] == 2


async def test_messages_count_active_conversations_are_distinct(
    client, create_user, create_conversation, create_message, login_as
):
    first = await create_conversation()
    second = await create_conversation()
    idle = await create_conversation()
    await create_message(conversation_id=first.id)
    await create_message(conversation_id=first.id)
    await create_message(conversation_id=second.id)
    await create_message(
        conversation_id=idle.id, created_at=datetime.now(UTC) - timedelta(days=2)
    )
    await _admin(client, create_user, login_as)

    response = await client.get("/api/v1/analytics/messages-count")

    body = response.json()
    assert body["activeConversationsToday"] == 2
    assert body["totalConversations"] == 3


async def test_messages_count_average_per_conversation(
    client, create_user, create_conversation, create_message, login_as
):
    first = await create_conversation()
    second = await create_conversation()
    for conversation_id in (first.id, first.id, first.id, second.id):
        await create_message(conversation_id=conversation_id)
    await _admin(client, create_user, login_as)

    response = await client.get("/api/v1/analytics/messages-count")

    assert response.json()["averageMessagesPerConversation"] == 2.0


async def test_messages_count_average_is_zero_without_conversations(
    client, create_user, login_as
):
    await _admin(client, create_user, login_as)

    response = await client.get("/api/v1/analytics/messages-count")

    assert response.status_code == 200
    body = response.json()
    assert body["totalConversations"] == 0
    assert body["averageMessagesPerConversation"] == 0.0


# top-liked


async def _favorite(create_listing_favorite, listing, times: int) -> None:
    for _ in range(times):
        await create_listing_favorite(listing_id=listing.id)


async def test_top_liked_ranks_by_favorite_count(
    client, create_user, create_listing, create_listing_favorite, login_as
):
    three = await create_listing(title="Trois")
    one = await create_listing(title="Un")
    two = await create_listing(title="Deux")
    await _favorite(create_listing_favorite, three, 3)
    await _favorite(create_listing_favorite, one, 1)
    await _favorite(create_listing_favorite, two, 2)
    await _admin(client, create_user, login_as)

    response = await client.get("/api/v1/analytics/top-liked")

    listings = response.json()["listings"]
    assert [
        (item["rank"], item["title"], item["favorites_count"]) for item in listings
    ] == [
        (1, "Trois", 3),
        (2, "Deux", 2),
        (3, "Un", 1),
    ]


async def test_top_liked_returns_at_most_five(
    client, create_user, create_listing, login_as
):
    for i in range(6):
        await create_listing(title=f"Annonce {i}")
    await _admin(client, create_user, login_as)

    response = await client.get("/api/v1/analytics/top-liked")

    assert len(response.json()["listings"]) == 5


async def test_top_liked_excludes_non_active_listings(
    client, create_user, create_listing, create_listing_favorite, login_as
):
    await create_listing(title="Active")
    sold = await create_listing(title="Vendue", status="sold")
    draft = await create_listing(title="Brouillon", status="draft")
    await _favorite(create_listing_favorite, sold, 3)
    await _favorite(create_listing_favorite, draft, 3)
    await _admin(client, create_user, login_as)

    response = await client.get("/api/v1/analytics/top-liked")

    assert [item["title"] for item in response.json()["listings"]] == ["Active"]


async def test_top_liked_keeps_snake_case_keys(
    client, create_user, create_listing, login_as
):
    listing = await create_listing()
    await _admin(client, create_user, login_as)

    response = await client.get("/api/v1/analytics/top-liked")

    item = response.json()["listings"][0]
    assert {"public_id", "favorites_count", "view_count"} <= item.keys()
    assert {"categoryName", "campusName", "imageUrl", "sellerName"} <= item.keys()
    assert "publicId" not in item
    assert "favoritesCount" not in item
    assert "viewCount" not in item
    assert item["id"] == str(listing.public_id)
    assert item["public_id"] == str(listing.public_id)


async def test_top_liked_image_url_is_the_cover_storage_path(
    client, db_session, create_user, create_listing, create_listing_image, login_as
):
    listing = await create_listing()
    await create_listing_image(
        listing_id=listing.id, storage_path="/mock/listings/other.jpg"
    )
    cover = await create_listing_image(
        listing_id=listing.id, storage_path="/mock/listings/cover.jpg", position=1
    )
    listing.cover_image_id = cover.id
    await db_session.flush()
    await _admin(client, create_user, login_as)

    response = await client.get("/api/v1/analytics/top-liked")

    assert response.json()["listings"][0]["imageUrl"] == "/mock/listings/cover.jpg"


async def test_top_liked_handles_listing_without_category_or_location(
    client, create_user, create_listing, login_as
):
    seller = await create_user(display_name="Camille R.")
    await create_listing(seller_id=seller.id)
    await _admin(client, create_user, login_as)

    response = await client.get("/api/v1/analytics/top-liked")

    assert response.status_code == 200
    item = response.json()["listings"][0]
    assert item["categoryName"] == "Autre"
    assert item["campusName"] == "—"
    assert item["sellerName"] == "Camille R."
    assert item["imageUrl"] is None


# dashboard


async def test_dashboard_returns_every_metric(client, create_user, login_as):
    await _admin(client, create_user, login_as)

    response = await client.get("/api/v1/analytics")

    assert set(response.json()) == {
        "onlineStudents",
        "listingsToday",
        "pendingReports",
        "soldPercentage",
        "categoryDistribution",
        "listingsBetweenDates",
        "totalValue",
        "averagePrice",
        "messagesCount",
        "topLiked",
    }


async def test_dashboard_forwards_date_range(client, create_user, login_as):
    await _admin(client, create_user, login_as)

    response = await client.get(
        "/api/v1/analytics", params={"startDate": "2026-01-10", "endDate": "2026-01-12"}
    )

    block = response.json()["listingsBetweenDates"]
    assert block["startDate"] == "2026-01-10"
    assert block["endDate"] == "2026-01-12"


async def test_dashboard_matches_individual_endpoints(
    client,
    create_user,
    create_category,
    create_listing,
    create_listing_favorite,
    create_conversation,
    create_message,
    create_report,
    login_as,
):
    category = await create_category(category_name="Informatique")
    active = await create_listing(price=100, category_id=category.id)
    await create_listing(price=250, status="sold", category_id=category.id)
    await create_listing(price=40)
    await create_listing_favorite(listing_id=active.id)
    conversation = await create_conversation(listing_id=active.id)
    await create_message(conversation_id=conversation.id)
    await create_report(reason="Arnaque")
    await _admin(client, create_user, login_as)

    dashboard = (await client.get("/api/v1/analytics")).json()

    for key, path in (
        ("listingsToday", "listings-today"),
        ("pendingReports", "pending-reports"),
        ("soldPercentage", "sold-percentage"),
        ("categoryDistribution", "category-distribution"),
        ("listingsBetweenDates", "listings-between-dates"),
        ("totalValue", "total-value"),
        ("averagePrice", "average-price"),
        ("messagesCount", "messages-count"),
        ("topLiked", "top-liked"),
    ):
        assert (
            dashboard[key] == (await client.get(f"/api/v1/analytics/{path}")).json()
        ), key


async def test_dashboard_works_on_empty_database(client, create_user, login_as):
    await _admin(client, create_user, login_as)

    response = await client.get("/api/v1/analytics")

    assert response.status_code == 200
    body = response.json()
    assert body["onlineStudents"]["total"] == 1
    assert body["listingsToday"]["count"] == 0
    assert body["pendingReports"]["count"] == 0
    assert body["soldPercentage"]["percentage"] == 0.0
    assert body["categoryDistribution"]["totalListings"] == 0
    assert body["listingsBetweenDates"]["totalCount"] == 0
    assert body["totalValue"]["totalValue"] == 0
    assert body["averagePrice"]["averagePrice"] == 0.0
    assert body["messagesCount"]["totalMessages"] == 0
    assert body["topLiked"]["listings"] == []
