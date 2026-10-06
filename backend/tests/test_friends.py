from datetime import UTC, datetime

import pytest
from sqlalchemy import select

from app.models import Friend, UserBlock


async def test_send_friend_request_requires_authentication(client, create_user):
    target = await create_user()

    response = await client.post("/api/v1/friends", json={"user_id": str(target.public_id)})

    assert response.status_code == 401


async def test_send_friend_request_creates_pending_request(client, create_user, login_as):
    login_as(await create_user())
    target = await create_user()

    response = await client.post("/api/v1/friends", json={"user_id": str(target.public_id)})

    assert response.status_code == 201
    assert response.json() == {"message": "Friend request sent"}


async def test_send_friend_request_returns_404_for_unknown_user(client, create_user, login_as):
    login_as(await create_user())

    response = await client.post(
        "/api/v1/friends", json={"user_id": "00000000-0000-0000-0000-000000000000"}
    )

    assert response.status_code == 404


async def test_send_friend_request_returns_400_for_self(client, create_user, login_as):
    me = await create_user()
    login_as(me)

    response = await client.post("/api/v1/friends", json={"user_id": str(me.public_id)})

    assert response.status_code == 400


@pytest.mark.parametrize("i_blocked", [True, False])
async def test_send_friend_request_returns_403_when_a_block_exists_either_way(
    client, db_session, create_user, login_as, i_blocked
):
    me = await create_user()
    login_as(me)
    target = await create_user()
    blocking, blocked = (me, target) if i_blocked else (target, me)
    db_session.add(UserBlock(user_blocking=blocking.id, user_blocked=blocked.id))
    await db_session.flush()

    response = await client.post("/api/v1/friends", json={"user_id": str(target.public_id)})

    assert response.status_code == 403
    assert await db_session.scalar(select(Friend).where(Friend.address_id == target.id)) is None


async def test_send_friend_request_is_allowed_again_once_the_block_is_lifted(
    client, create_user, login_as
):
    me = await create_user()
    login_as(me)
    target = await create_user()
    await client.post(f"/api/v1/users/{target.public_id}/block")
    await client.delete(f"/api/v1/users/{target.public_id}/block")

    response = await client.post("/api/v1/friends", json={"user_id": str(target.public_id)})

    assert response.status_code == 201


async def test_send_friend_request_returns_409_for_existing_request(
    client, create_user, create_friend, login_as
):
    me = await create_user()
    login_as(me)
    target = await create_user()
    await create_friend(requester_id=me.id, address_id=target.id)

    response = await client.post("/api/v1/friends", json={"user_id": str(target.public_id)})

    assert response.status_code == 409


async def test_list_pending_friend_requests_requires_authentication(client):
    response = await client.get("/api/v1/friends/pending")

    assert response.status_code == 401


async def test_list_pending_friend_requests_returns_only_requests_addressed_to_me(
    client, create_user, create_friend, login_as
):
    me = await create_user()
    login_as(me)
    requester = await create_user(display_name="Alice")
    request = await create_friend(requester_id=requester.id, address_id=me.id)
    await create_friend(address_id=(await create_user()).id)  # not mine

    response = await client.get("/api/v1/friends/pending")

    assert response.status_code == 200
    body = response.json()
    assert len(body) == 1
    assert body[0]["id"] == str(request.id)
    assert body[0]["status"] == "pending"
    assert body[0]["requester_id"] == str(requester.public_id)
    assert body[0]["address_id"] == str(me.public_id)
    assert body[0]["addressee_id"] == str(me.public_id)
    assert body[0]["requester"]["display_name"] == "Alice"
    assert body[0]["addressee"]["display_name"] == me.display_name


async def test_list_pending_friend_requests_excludes_already_accepted(
    client, create_user, create_friend, login_as
):
    me = await create_user()
    login_as(me)
    await create_friend(address_id=me.id, status="accepted")

    response = await client.get("/api/v1/friends/pending")

    assert response.json() == []


async def test_list_pending_friend_requests_excludes_blocked_requesters(
    client, db_session, create_user, create_friend, login_as
):
    me = await create_user()
    login_as(me)
    blocked = await create_user(display_name="Blocked")
    allowed = await create_user(display_name="Allowed")
    await create_friend(requester_id=blocked.id, address_id=me.id)
    kept = await create_friend(requester_id=allowed.id, address_id=me.id)
    db_session.add(UserBlock(user_blocking=me.id, user_blocked=blocked.id))
    await db_session.flush()

    response = await client.get("/api/v1/friends/pending")

    assert response.status_code == 200
    body = response.json()
    assert [item["id"] for item in body] == [str(kept.id)]
    assert body[0]["requester_id"] == str(allowed.public_id)

async def test_list_pending_friend_requests_excludes_deleted_requesters(
    client, create_user, create_friend, login_as
):
    me = await create_user()
    login_as(me)
    gone = await create_user(deleted_at=datetime.now(UTC))
    await create_friend(requester_id=gone.id, address_id=me.id)

    response = await client.get("/api/v1/friends/pending")

    assert response.json() == []

async def test_accept_friend_request(client, db_session, create_user, create_friend, login_as):
    me = await create_user()
    login_as(me)
    request = await create_friend(address_id=me.id)

    response = await client.post(f"/api/v1/friends/{request.id}/accept")

    assert response.status_code == 200
    assert response.json() == {"message": "Friend request accepted"}
    await db_session.refresh(request)
    assert request.status == "accepted"
    assert request.responded_at is not None


async def test_accept_friend_request_returns_404_when_not_addressed_to_current_user(
    client, create_user, create_friend, login_as
):
    login_as(await create_user())
    request = await create_friend()

    response = await client.post(f"/api/v1/friends/{request.id}/accept")

    assert response.status_code == 404


async def test_decline_friend_request_deletes_it(client, db_session, create_user, create_friend, login_as):
    me = await create_user()
    login_as(me)
    request = await create_friend(address_id=me.id)

    response = await client.post(f"/api/v1/friends/{request.id}/decline")

    assert response.status_code == 200
    remaining = await db_session.scalar(select(Friend).where(Friend.id == request.id))
    assert remaining is None


async def test_cancel_friend_request_requires_authentication(client, create_user):
    target = await create_user()

    response = await client.delete(f"/api/v1/friends/requests/{target.public_id}")

    assert response.status_code == 401


async def test_cancel_friend_request_deletes_my_own_pending_request(
    client, db_session, create_user, create_friend, login_as
):
    me = await create_user()
    login_as(me)
    target = await create_user()
    request = await create_friend(requester_id=me.id, address_id=target.id, status="pending")

    response = await client.delete(f"/api/v1/friends/requests/{target.public_id}")

    assert response.status_code == 200
    remaining = await db_session.scalar(select(Friend).where(Friend.id == request.id))
    assert remaining is None


async def test_cancel_friend_request_returns_404_for_a_request_i_received(
    client, create_user, create_friend, login_as
):
    me = await create_user()
    login_as(me)
    requester = await create_user()
    # requester sent it to me - I can't "cancel" a request that's mine to
    # accept/decline, only one I sent myself.
    await create_friend(requester_id=requester.id, address_id=me.id, status="pending")

    response = await client.delete(f"/api/v1/friends/requests/{requester.public_id}")

    assert response.status_code == 404


async def test_cancel_friend_request_returns_404_for_an_already_accepted_request(
    client, create_user, create_friend, login_as
):
    me = await create_user()
    login_as(me)
    target = await create_user()
    await create_friend(requester_id=me.id, address_id=target.id, status="accepted")

    response = await client.delete(f"/api/v1/friends/requests/{target.public_id}")

    assert response.status_code == 404


async def test_cancel_friend_request_returns_404_for_unknown_user(client, create_user, login_as):
    login_as(await create_user())

    response = await client.delete(
        "/api/v1/friends/requests/00000000-0000-0000-0000-000000000000"
    )

    assert response.status_code == 404


async def test_remove_friend(client, create_user, create_friend, login_as):
    me = await create_user()
    login_as(me)
    other = await create_user()
    await create_friend(requester_id=me.id, address_id=other.id, status="accepted")

    response = await client.delete(f"/api/v1/friends/{other.public_id}")

    assert response.status_code == 200
    assert response.json() == {"message": "Friend removed"}


async def test_remove_friend_returns_404_when_not_friends(client, create_user, login_as):
    login_as(await create_user())
    stranger = await create_user()

    response = await client.delete(f"/api/v1/friends/{stranger.public_id}")

    assert response.status_code == 404


async def test_send_friend_message_requires_authentication(client, create_user):
    friend = await create_user()

    response = await client.post(
        f"/api/v1/friends/{friend.public_id}/messages", json={"body": "Salut"}
    )

    assert response.status_code == 401


async def test_send_friend_message_returns_404_when_not_friends(client, create_user, login_as):
    login_as(await create_user())
    stranger = await create_user()

    response = await client.post(
        f"/api/v1/friends/{stranger.public_id}/messages", json={"body": "Salut"}
    )

    assert response.status_code == 404


async def test_send_friend_message_returns_404_for_pending_request(
    client, create_user, create_friend, login_as
):
    me = await create_user()
    login_as(me)
    other = await create_user()
    await create_friend(requester_id=me.id, address_id=other.id, status="pending")

    response = await client.post(
        f"/api/v1/friends/{other.public_id}/messages", json={"body": "Salut"}
    )

    assert response.status_code == 404


async def test_send_friend_message_persists_and_appears_in_history(
    client, create_user, create_friend, login_as
):
    me = await create_user()
    login_as(me)
    other = await create_user()
    await create_friend(requester_id=me.id, address_id=other.id, status="accepted")

    response = await client.post(
        f"/api/v1/friends/{other.public_id}/messages", json={"body": "Toujours dispo ce soir ?"}
    )

    assert response.status_code == 201
    body = response.json()
    assert body["body"] == "Toujours dispo ce soir ?"
    assert body["sender_id"] == str(me.public_id)

    history = await client.get(f"/api/v1/friends/{other.public_id}/messages")
    assert history.status_code == 200
    assert [m["body"] for m in history.json()] == ["Toujours dispo ce soir ?"]


async def test_send_friend_message_returns_403_when_recipient_blocked_sender(
    client, db_session, create_user, create_friend, login_as
):
    me = await create_user()
    login_as(me)
    other = await create_user()
    await create_friend(requester_id=me.id, address_id=other.id, status="accepted")
    db_session.add(UserBlock(user_blocking=other.id, user_blocked=me.id))
    await db_session.flush()

    response = await client.post(
        f"/api/v1/friends/{other.public_id}/messages", json={"body": "Hello"}
    )

    assert response.status_code == 403


async def test_send_friend_message_returns_403_when_sender_blocked_recipient(
    client, db_session, create_user, create_friend, login_as
):
    me = await create_user()
    login_as(me)
    other = await create_user()
    await create_friend(requester_id=me.id, address_id=other.id, status="accepted")
    db_session.add(UserBlock(user_blocking=me.id, user_blocked=other.id))
    await db_session.flush()

    response = await client.post(
        f"/api/v1/friends/{other.public_id}/messages", json={"body": "Hello"}
    )

    assert response.status_code == 403


async def test_list_friend_messages_requires_authentication(client, create_user):
    friend = await create_user()

    response = await client.get(f"/api/v1/friends/{friend.public_id}/messages")

    assert response.status_code == 401


async def test_list_friend_messages_returns_404_when_not_friends(client, create_user, login_as):
    login_as(await create_user())
    stranger = await create_user()

    response = await client.get(f"/api/v1/friends/{stranger.public_id}/messages")

    assert response.status_code == 404


async def test_list_friend_conversations_requires_authentication(client):
    response = await client.get("/api/v1/friends/messages")

    assert response.status_code == 401


async def test_list_friend_conversations_returns_only_accepted_with_last_message(
    client, create_user, create_friend, login_as
):
    me = await create_user()
    login_as(me)
    accepted = await create_user(display_name="Ami accepté")
    pending = await create_user(display_name="Demande en attente")
    await create_friend(requester_id=me.id, address_id=accepted.id, status="accepted")
    await create_friend(requester_id=me.id, address_id=pending.id, status="pending")

    await client.post(f"/api/v1/friends/{accepted.public_id}/messages", json={"body": "Yo"})

    response = await client.get("/api/v1/friends/messages")

    assert response.status_code == 200
    body = response.json()
    assert len(body) == 1
    assert body[0]["type"] == "friend"
    assert body[0]["other_participant"]["display_name"] == "Ami accepté"
    assert body[0]["last_message"]["body"] == "Yo"
