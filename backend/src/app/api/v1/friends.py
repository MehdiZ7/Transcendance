import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import Select, and_, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.db import get_session
from app.core.quotas import enforce
from app.core.ratelimit import limit_friend_requests, limit_messages
from app.core.realtime.hub import Hub
from app.core.security import get_current_user
from app.core.serializers import to_public_user
from app.models import Friend, FriendMessage, User, UserBlock
from app.realtime import get_hub
from app.realtime_topics import publish_to_users
from app.schemas.common import MessageResponse
from app.schemas.friend import (
    FriendConversationSummary,
    FriendMessageCreate,
    FriendMessageRead,
    FriendRead,
    FriendRequestCreate,
)
from app.schemas.limits import BeforeId, PathId

router = APIRouter()


async def _require_friendship(
    session: AsyncSession, current_user_id: int, other_id: int
) -> Friend:
    friendship = await session.scalar(
        select(Friend).where(
            Friend.status == "accepted",
            or_(
                and_(
                    Friend.requester_id == current_user_id,
                    Friend.address_id == other_id,
                ),
                and_(
                    Friend.requester_id == other_id,
                    Friend.address_id == current_user_id,
                ),
            ),
        )
    )
    if friendship is None:
        # 404 rather than 403 - don't reveal whether a pending/declined
        # request exists between the two.
        raise HTTPException(status_code=404, detail="Friendship not found")
    return friendship


async def _require_not_blocked(
    session: AsyncSession,
    user_a: int,
    user_b: int,
    detail: str = "Cannot message a blocked user",
) -> None:
    blocked = await session.scalar(
        select(UserBlock.user_blocking).where(
            or_(
                and_(
                    UserBlock.user_blocking == user_a, UserBlock.user_blocked == user_b
                ),
                and_(
                    UserBlock.user_blocking == user_b, UserBlock.user_blocked == user_a
                ),
            )
        )
    )
    if blocked is not None:
        raise HTTPException(status_code=403, detail=detail)


def _to_friend_message_read(
    message: FriendMessage, friend_id: int, sender_public_id: uuid.UUID
) -> FriendMessageRead:
    return FriendMessageRead(
        id=message.id,
        friend_id=friend_id,
        sender_id=sender_public_id,
        body=message.body,
        created_at=message.created_at,
        edited_at=message.edited_at,
        deleted_at=message.deleted_at,
    )


def _friends_count(user_id: int) -> Select:
    """Accepted friendships of `user_id`, in either direction: what quota_friends caps."""
    return (
        select(func.count())
        .select_from(Friend)
        .where(
            Friend.status == "accepted",
            or_(Friend.requester_id == user_id, Friend.address_id == user_id),
        )
    )


@router.post("/friends", status_code=201, dependencies=[Depends(limit_friend_requests)])
async def send_friend_request(
    payload: FriendRequestCreate,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> MessageResponse:
    target = await session.scalar(select(User).where(User.public_id == payload.user_id))
    if target is None:
        raise HTTPException(status_code=404, detail="User not found")
    if target.id == current_user.id:
        raise HTTPException(
            status_code=400, detail="Cannot send a friend request to yourself"
        )
    # Either direction: whoever blocked, and whoever was blocked, has no way
    # back to a friendship until the block is lifted (blocking deleted it)
    await _require_not_blocked(
        session,
        current_user.id,
        target.id,
        detail="Cannot send a friend request to a blocked user",
    )

    existing = await session.scalar(
        select(Friend).where(
            or_(
                and_(
                    Friend.requester_id == current_user.id,
                    Friend.address_id == target.id,
                ),
                and_(
                    Friend.requester_id == target.id,
                    Friend.address_id == current_user.id,
                ),
            )
        )
    )
    if existing is not None:
        raise HTTPException(
            status_code=409,
            detail="A friend request already exists between these users",
        )
    await enforce(
        session,
        current_user.id,
        select(func.count()).select_from(Friend).where(
            Friend.requester_id == current_user.id, Friend.status == "pending"
        ),
        settings.quota_pending_friend_requests,
        "Too many pending friend requests: wait for answers or cancel some",
    )
    await enforce(
        session,
        current_user.id,
        _friends_count(current_user.id),
        settings.quota_friends,
        "Too many friends",
    )

    session.add(
        Friend(requester_id=current_user.id, address_id=target.id, status="pending")
    )
    await session.commit()
    return MessageResponse(message="Friend request sent")


@router.get("/friends/pending")
async def list_pending_friend_requests(
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> list[FriendRead]:
    """Friend requests received by the current user and still awaiting a
    response - the id accept/decline need. Outgoing requests the current
    user sent are out of scope for now.
    Requests from deleted users or users the current user has blocked are hidden."""
    blocked_ids = select(UserBlock.user_blocked).where(
        UserBlock.user_blocking == current_user.id
    )
    result = await session.execute(
        select(Friend, User)
        .join(User, User.id == Friend.requester_id)
        .where(
            Friend.address_id == current_user.id,
            Friend.status == "pending",
            Friend.requester_id.not_in(blocked_ids),
            User.deleted_at.is_(None),
        )
        .order_by(Friend.created_at.desc())
    )
    return [
        FriendRead(
            id=str(request.id),
            requester_id=requester.public_id,
            address_id=current_user.public_id,
            addressee_id=current_user.public_id,
            status=request.status,
            created_at=request.created_at,
            responded_at=request.responded_at,
            requester=to_public_user(requester),
            addressee=to_public_user(current_user),
        )
        for request, requester in result.all()
    ]


@router.post("/friends/{request_id}/accept")
async def accept_friend_request(
    request_id: PathId,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> MessageResponse:
    request = await session.scalar(
        select(Friend).where(
            Friend.id == request_id, Friend.address_id == current_user.id
        )
    )
    if request is None:
        raise HTTPException(status_code=404, detail="Friend request not found")
    if request.status != "pending":
        raise HTTPException(status_code=409, detail="Friend request is not pending")
    # The friendship counts for both users. Their rows are locked in id order,
    # so two accepts involving the same users can never wait on each other
    for user_id in sorted((current_user.id, request.requester_id)):
        await enforce(
            session,
            user_id,
            _friends_count(user_id),
            settings.quota_friends,
            "Too many friends" if user_id == current_user.id else "This user has too many friends",
        )

    request.status = "accepted"
    request.responded_at = datetime.now(UTC)
    await session.commit()
    return MessageResponse(message="Friend request accepted")


@router.post("/friends/{request_id}/decline")
async def decline_friend_request(
    request_id: PathId,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> MessageResponse:
    request = await session.scalar(
        select(Friend).where(
            Friend.id == request_id, Friend.address_id == current_user.id
        )
    )
    if request is None:
        raise HTTPException(status_code=404, detail="Friend request not found")

    # Friend.status has no 'declined' option in its CHECK constraint, so
    # declining just deletes the pending request instead of keeping history.
    await session.delete(request)
    await session.commit()
    return MessageResponse(message="Friend request declined")


@router.delete("/friends/requests/{public_id}")
async def cancel_friend_request(
    public_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> MessageResponse:
    """Cancel a pending request the current user sent - the requester's side
    of accept/decline, which only the addressee can do."""
    target = await session.scalar(select(User).where(User.public_id == public_id))
    if target is None:
        raise HTTPException(status_code=404, detail="User not found")

    request = await session.scalar(
        select(Friend).where(
            Friend.requester_id == current_user.id,
            Friend.address_id == target.id,
            Friend.status == "pending",
        )
    )
    if request is None:
        raise HTTPException(status_code=404, detail="Pending friend request not found")

    await session.delete(request)
    await session.commit()
    return MessageResponse(message="Friend request cancelled")


@router.delete("/friends/{public_id}")
async def remove_friend(
    public_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> MessageResponse:
    target = await session.scalar(select(User).where(User.public_id == public_id))
    if target is None:
        raise HTTPException(status_code=404, detail="User not found")

    friendship = await _require_friendship(session, current_user.id, target.id)

    await session.delete(friendship)
    await session.commit()
    return MessageResponse(message="Friend removed")


@router.get("/friends/messages")
async def list_friend_conversations(
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> list[FriendConversationSummary]:
    result = await session.execute(
        select(Friend).where(
            Friend.status == "accepted",
            or_(
                Friend.requester_id == current_user.id,
                Friend.address_id == current_user.id,
            ),
        )
    )
    friendships = result.scalars().all()

    summaries = []
    for friendship in friendships:
        other_id = (
            friendship.address_id
            if friendship.requester_id == current_user.id
            else friendship.requester_id
        )
        other = await session.scalar(select(User).where(User.id == other_id))

        last = await session.scalar(
            select(FriendMessage)
            .where(FriendMessage.conversation_id == friendship.id)
            .order_by(FriendMessage.created_at.desc(), FriendMessage.id.desc())
            .limit(1)
        )
        last_message = None
        if last is not None:
            sender_public_id = await session.scalar(
                select(User.public_id).where(User.id == last.sender_id)
            )
            last_message = _to_friend_message_read(
                last, friendship.id, sender_public_id
            )

        summaries.append(
            FriendConversationSummary(
                friend_id=friendship.id,
                other_participant=to_public_user(other),
                last_message=last_message,
                updated_at=last.created_at
                if last
                else (friendship.responded_at or friendship.created_at),
            )
        )

    summaries.sort(key=lambda summary: summary.updated_at, reverse=True)
    return summaries


@router.get("/friends/{public_id}/messages")
async def list_friend_messages(
    public_id: uuid.UUID,
    limit: int = Query(30, ge=1, le=100),
    before_id: BeforeId = None,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> list[FriendMessageRead]:
    other = await session.scalar(select(User).where(User.public_id == public_id))
    if other is None:
        raise HTTPException(status_code=404, detail="User not found")
    friendship = await _require_friendship(session, current_user.id, other.id)

    conditions = [FriendMessage.conversation_id == friendship.id]
    if before_id is not None:
        conditions.append(FriendMessage.id < before_id)

    result = await session.execute(
        select(FriendMessage, User.public_id)
        .join(User, User.id == FriendMessage.sender_id)
        .where(*conditions)
        .order_by(FriendMessage.created_at.desc(), FriendMessage.id.desc())
        .limit(limit)
    )
    # query is newest-first to fetch the latest page efficiently with
    # before_id, but the chat UI expects chronological (oldest-first) order.
    rows = list(reversed(result.all()))
    return [
        _to_friend_message_read(message, friendship.id, sender_public_id)
        for message, sender_public_id in rows
    ]


@router.post(
    "/friends/{public_id}/messages",
    status_code=201,
    dependencies=[Depends(limit_messages)],
)
async def send_friend_message(
    public_id: uuid.UUID,
    payload: FriendMessageCreate,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
    hub: Hub = Depends(get_hub),
) -> FriendMessageRead:
    other = await session.scalar(select(User).where(User.public_id == public_id))
    if other is None:
        raise HTTPException(status_code=404, detail="User not found")
    friendship = await _require_friendship(session, current_user.id, other.id)
    await _require_not_blocked(session, current_user.id, other.id)
    await enforce(
        session,
        current_user.id,
        select(func.count()).select_from(FriendMessage).where(
            FriendMessage.conversation_id == friendship.id
        ),
        settings.quota_messages_per_conversation,
        "This conversation is full",
        lock=False,
    )

    message = FriendMessage(
        conversation_id=friendship.id,
        sender_id=current_user.id,
        body=payload.body,
    )
    session.add(message)
    await session.commit()

    read = _to_friend_message_read(message, friendship.id, current_user.public_id)
    # to both participants: the sender's other tabs need it too
    publish_to_users(
        hub,
        "friend_message.created",
        (str(current_user.public_id), str(other.public_id)),
        read.model_dump(mode="json"),
    )
    return read
