"""REST rate limiting (app/core/ratelimit.py)."""

import pytest

from app.core.config import settings
from app.core.ratelimit import HOUR, MINUTE, SlidingWindow


class Clock:
    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now


@pytest.fixture
def setting(monkeypatch):
    def _set(name: str, value: int) -> None:
        monkeypatch.setattr(settings, f"rate_{name}", value)

    return _set


# ── the sliding window ────────────────────────────────────────────


def test_window_allows_up_to_the_limit_then_says_how_long_to_wait():
    clock = Clock()
    window = SlidingWindow(clock)

    assert [window.hit(("b", "u"), 2, 60) for _ in range(2)] == [None, None]
    clock.now += 20
    assert window.hit(("b", "u"), 2, 60) == pytest.approx(40)


def test_window_lets_requests_through_again_once_they_age_out():
    clock = Clock()
    window = SlidingWindow(clock)
    window.hit(("b", "u"), 1, 60)
    assert window.hit(("b", "u"), 1, 60) is not None

    clock.now += 60

    assert window.hit(("b", "u"), 1, 60) is None


def test_window_keys_are_independent():
    window = SlidingWindow(Clock())
    window.hit(("messages", "alice"), 1, 60)

    assert window.hit(("messages", "alice"), 1, 60) is not None
    assert window.hit(("messages", "bob"), 1, 60) is None
    assert window.hit(("listings", "alice"), 1, 60) is None


def test_refused_hits_do_not_extend_the_wait():
    clock = Clock()
    window = SlidingWindow(clock)
    window.hit(("b", "u"), 1, 60)

    for _ in range(50):
        clock.now += 1
        window.hit(("b", "u"), 1, 60)

    # 50 s spent hammering: the first hit still leaves the window at 60 s
    assert window.hit(("b", "u"), 1, 60) == pytest.approx(10)


def test_idle_keys_are_forgotten_and_busy_ones_kept():
    clock = Clock()
    window = SlidingWindow(clock)
    window.hit(("b", "gone"), 5, 60)
    window.hit(("b", "hour"), 5, HOUR)

    clock.now += 2 * MINUTE
    window.hit(("b", "trigger"), 5, 60)  # the sweep runs on a hit

    assert set(window._hits) == {("b", "hour"), ("b", "trigger")}


# ── the routes ────────────────────────────────────────────────────


async def test_reads_are_limited_per_user_with_retry_after(client, create_user, login_as, setting):
    login_as(await create_user())
    setting("reads_per_minute", 2)

    statuses = [(await client.get("/api/v1/users/me")).status_code for _ in range(3)]
    refused = await client.get("/api/v1/users/me")

    assert statuses == [200, 200, 429]
    assert 1 <= int(refused.headers["retry-after"]) <= 60


async def test_writes_are_limited_separately_from_reads(client, create_user, login_as, setting):
    login_as(await create_user())
    setting("writes_per_minute", 2)
    setting("reads_per_minute", 1000)

    writes = [
        (await client.patch("/api/v1/users/me", json={"bio": "x"})).status_code for _ in range(3)
    ]
    read = await client.get("/api/v1/users/me")

    assert writes == [200, 200, 429]
    assert read.status_code == 200


async def test_one_users_requests_do_not_count_for_another(client, create_user, login_as, setting):
    busy, calm = await create_user(), await create_user()
    setting("reads_per_minute", 1)
    login_as(busy)
    await client.get("/api/v1/users/me")
    assert (await client.get("/api/v1/users/me")).status_code == 429

    login_as(calm)

    assert (await client.get("/api/v1/users/me")).status_code == 200


async def test_requests_without_a_session_are_not_limited_here(client, setting):
    setting("reads_per_minute", 1)

    statuses = [(await client.get("/api/v1/listings")).status_code for _ in range(4)]

    assert statuses == [200] * 4


async def test_a_limit_of_zero_turns_the_bucket_off(client, create_user, login_as, setting):
    login_as(await create_user())
    setting("reads_per_minute", 0)

    statuses = [(await client.get("/api/v1/users/me")).status_code for _ in range(5)]

    assert statuses == [200] * 5


async def test_a_garbage_session_is_not_rate_limited(client, setting):
    setting("reads_per_minute", 1)
    client.cookies.set(settings.session_cookie_name, "not.a.jwt")

    # /users/me, not /auth/me: the latter requires a real session (401 on
    # garbage), /users/me is the anonymous-safe one (204) - that's the point
    # of this test, a garbage session must not get treated as a 429 either.
    statuses = [(await client.get("/api/v1/users/me")).status_code for _ in range(3)]

    assert statuses == [204] * 3


async def test_message_bucket_is_shared_by_listing_chats_and_friend_dms(
    client, create_user, create_conversation, create_friend, login_as, setting
):
    me = await create_user()
    login_as(me)
    setting("messages_per_minute", 1)
    conversation = await create_conversation(buyer_id=me.id)
    friend = await create_user()
    await create_friend(requester_id=me.id, address_id=friend.id, status="accepted")

    first = await client.post(
        f"/api/v1/conversations/{conversation.id}/messages", json={"body": "hi"}
    )
    second = await client.post(f"/api/v1/friends/{friend.public_id}/messages", json={"body": "yo"})

    assert first.status_code == 201
    assert second.status_code == 429


async def test_a_refused_message_is_not_stored(
    client, create_user, create_conversation, login_as, setting
):
    me = await create_user()
    login_as(me)
    setting("messages_per_minute", 1)
    conversation = await create_conversation(buyer_id=me.id)
    url = f"/api/v1/conversations/{conversation.id}/messages"
    await client.post(url, json={"body": "one"})

    refused = await client.post(url, json={"body": "two"})
    history = await client.get(url)

    assert refused.status_code == 429
    assert [m["body"] for m in history.json()] == ["one"]


async def test_listing_creation_is_limited_per_hour(
    client, create_user, listing_payload, login_as, setting
):
    login_as(await create_user())
    setting("listings_per_hour", 1)

    first = await client.post("/api/v1/listings", json=await listing_payload())
    second = await client.post("/api/v1/listings", json=await listing_payload())

    assert (first.status_code, second.status_code) == (201, 429)


async def test_report_creation_is_limited_per_hour(
    client, create_user, create_listing, login_as, setting
):
    login_as(await create_user())
    setting("reports_per_hour", 1)
    first_target, second_target = await create_listing(), await create_listing()

    def body(target):
        return {"target_type": "listing", "target_id": str(target.public_id), "reason": "spam"}

    first = await client.post("/api/v1/reports", json=body(first_target))
    second = await client.post("/api/v1/reports", json=body(second_target))

    assert (first.status_code, second.status_code) == (201, 429)


async def test_friend_requests_are_limited_per_hour(client, create_user, login_as, setting):
    login_as(await create_user())
    setting("friend_requests_per_hour", 1)
    a, b = await create_user(), await create_user()

    first = await client.post("/api/v1/friends", json={"user_id": str(a.public_id)})
    second = await client.post("/api/v1/friends", json={"user_id": str(b.public_id)})

    assert (first.status_code, second.status_code) == (201, 429)
