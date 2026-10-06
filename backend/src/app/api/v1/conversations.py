from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy import and_, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from app.core.config import settings
from app.core.analytics_bus import analytics_bus
from app.core.db import get_session
from app.core.quotas import enforce, since_window
from app.core.ratelimit import limit_messages
from app.core.realtime.hub import Hub
from app.core.security import get_current_user
from app.core.serializers import to_public_user
from app.models import (
    Conversation,
    Listing,
    ListingImage,
    Message,
    Review,
    User,
    UserBlock,
)
from app.models.enums import ListingStatus
from app.realtime import get_hub
from app.realtime_topics import publish_to_users, remember_participants
from app.schemas.conversation import (
    ConversationCreate,
    ConversationSummary,
    MarkSoldResponse,
    MessageCreate,
    MessageRead,
)
from app.schemas.limits import BeforeId, PathId

router = APIRouter()


def _to_message_read(message: Message, sender_public_id) -> MessageRead:
    return MessageRead(
        id=message.id,
        conversation_id=message.conversation_id,
        sender_id=sender_public_id,
        body=message.body,
        created_at=message.created_at,
        edited_at=message.edited_at,
        deleted_at=message.deleted_at,
    )


async def _require_conversation(
    session: AsyncSession, conversation_id: int, user_id: int
) -> Conversation:
    conversation = await session.scalar(
        select(Conversation).where(
            Conversation.id == conversation_id,
            or_(Conversation.buyer_id == user_id, Conversation.seller_id == user_id),
        )
    )
    if conversation is None:
        # 404 rather than 403 - don't reveal whether the conversation exists.
        raise HTTPException(status_code=404, detail="Conversation not found")
    return conversation


def _other_participant_id(conversation: Conversation, user_id: int) -> int:
    return (
        conversation.seller_id if conversation.buyer_id == user_id else conversation.buyer_id
    )


async def _require_not_blocked(session: AsyncSession, user_a: int, user_b: int) -> None:
    blocked = await session.scalar(
        select(UserBlock.user_blocking).where(
            or_(
                and_(UserBlock.user_blocking == user_a, UserBlock.user_blocked == user_b),
                and_(UserBlock.user_blocking == user_b, UserBlock.user_blocked == user_a),
            )
        )
    )
    if blocked is not None:
        raise HTTPException(status_code=403, detail="Cannot message a blocked user")


async def _buyer_has_reviewed(
    session: AsyncSession,
    conversation: Conversation
) -> bool:
    return (
        await session.scalar(
            select(Review.id).where(
                Review.conversation_id == conversation.id,
                Review.author_id == conversation.buyer_id,
            )
        )
        is not None
    )

async def _to_summary(
    session: AsyncSession,
    conversation: Conversation,
    current_user: User,
    listing: Listing | None = None,
) -> ConversationSummary:
    if listing is None:
        listing = await session.scalar(select(Listing).where(Listing.id == conversation.listing_id))

    other_id = _other_participant_id(conversation, current_user.id)
    other_user = await session.scalar(select(User).where(User.id == other_id))

    last_message_row = await session.scalar(
        select(Message)
        .where(Message.conversation_id == conversation.id)
        .order_by(Message.created_at.desc(), Message.id.desc())
        .limit(1)
    )
    last_message = None
    if last_message_row is not None:
        sender_public_id = await session.scalar(
            select(User.public_id).where(User.id == last_message_row.sender_id)
        )
        last_message = _to_message_read(last_message_row, sender_public_id)

    cover_image_path = None
    if listing.cover_image_id is not None:
        cover_image_path = await session.scalar(
            select(ListingImage.storage_path).where(
                ListingImage.id == listing.cover_image_id
            )
        )

    seller = current_user if current_user.id == conversation.seller_id else other_user
    buyer = current_user if current_user.id == conversation.buyer_id else other_user
    sold_here = (
        listing.status == ListingStatus.SOLD and listing.buyer_id == conversation.buyer_id
    )

    return ConversationSummary(
        id=conversation.id,
        listing_id=listing.id,
        listing_public_id=listing.public_id,
        listing_title=listing.title,
        listing_cover_image=cover_image_path,
        other_participant=to_public_user(other_user) if other_user else to_public_user(current_user),
        last_message=last_message,
        is_closed=conversation.closed,
        updated_at=last_message_row.created_at if last_message_row else conversation.created_at,
        listing_status=listing.status,
        listing_seller_id=seller.public_id,
        listing_buyer_id=buyer.public_id if sold_here else None,
        has_reviewed=await _buyer_has_reviewed(session, conversation),
    )


@router.post("/conversations/listing", status_code=201)
async def create_or_get_listing_conversation(
    payload: ConversationCreate,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> ConversationSummary:
    listing = await session.scalar(
        select(Listing)
        .options(joinedload(Listing.seller))
        .where(Listing.public_id == payload.listing_id)
    )
    if listing is None:
        raise HTTPException(status_code=404, detail="Listing not found")
    if listing.seller_id == current_user.id:
        raise HTTPException(status_code=400, detail="Cannot start a conversation with yourself")
    await _require_not_blocked(session, current_user.id, listing.seller_id)

    conversation = await session.scalar(
        select(Conversation).where(
            Conversation.listing_id == listing.id, Conversation.buyer_id == current_user.id
        )
    )
    if conversation is None:
        await enforce(
            session,
            current_user.id,
            select(func.count()).select_from(Conversation).where(
                Conversation.buyer_id == current_user.id,
                Conversation.created_at > since_window(),
            ),
            settings.quota_conversations_per_day,
            "Too many conversations opened today, try again later",
            status_code=429,
        )
        conversation = Conversation(
            listing_id=listing.id, seller_id=listing.seller_id, buyer_id=current_user.id
        )
        session.add(conversation)
        await session.commit()

    return await _to_summary(session, conversation, current_user, listing=listing)


@router.get("/conversations")
async def list_conversations(
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> list[ConversationSummary]:
    result = await session.execute(
        select(Conversation)
        .where(
            or_(
                Conversation.buyer_id == current_user.id,
                Conversation.seller_id == current_user.id,
            )
        )
        .order_by(Conversation.created_at.desc())
    )
    conversations = result.scalars().all()
    return [await _to_summary(session, conversation, current_user) for conversation in conversations]


@router.delete("/conversations/{conversation_id}", status_code=204)
async def close_conversation(
    conversation_id: PathId,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> Response:
    conversation = await _require_conversation(session, conversation_id, current_user.id)
    conversation.closed = True
    await session.commit()
    return Response(status_code=204)


@router.post("/conversations/{conversation_id}/mark-sold")
async def mark_sold(
    conversation_id: PathId,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> MarkSoldResponse:
    conversation = await _require_conversation(session, conversation_id, current_user.id)
    if current_user.id != conversation.seller_id:
        raise HTTPException(status_code=403, detail="Only the seller can mark a listing as sold")

    listing = await session.scalar(select(Listing).where(Listing.id == conversation.listing_id))
    if listing is None:
        raise HTTPException(status_code=404, detail="Listing not found")
    if listing.status != ListingStatus.ACTIVE:
        # Blocks re-marking a listing sold from a different conversation
        # (another buyer who never bought it) once it's already sold - see
        # the POST /reviews sold-check, which trusts listings.buyer_id.
        raise HTTPException(status_code=409, detail="Listing is not active")

    listing.status = ListingStatus.SOLD
    listing.buyer_id = conversation.buyer_id
    listing.updated_at = datetime.now(UTC)
    await session.flush()

    result = await session.execute(
        select(Listing)
        .where(Listing.id == listing.id)
        .options(joinedload(Listing.seller), joinedload(Listing.buyer))
    )
    listing = result.unique().scalar_one()

    has_reviewed = await _buyer_has_reviewed(session, conversation)

    await session.commit()
    analytics_bus.publish("listing.sold")

    return MarkSoldResponse(
        id=conversation.id,
        listing_id=listing.id,
        listing_public_id=listing.public_id,
        listing_title=listing.title,
        listing_status=listing.status,
        listing_seller_id=listing.seller.public_id,
        listing_buyer_id=listing.buyer.public_id,
        has_reviewed=has_reviewed,
    )


@router.get("/conversations/{conversation_id}/messages")
async def list_messages(
    conversation_id: PathId,
    limit: int = Query(30, ge=1, le=100),
    before_id: BeforeId = None,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> list[MessageRead]:
    await _require_conversation(session, conversation_id, current_user.id)

    conditions = [Message.conversation_id == conversation_id]
    if before_id is not None:
        conditions.append(Message.id < before_id)

    result = await session.execute(
        select(Message, User.public_id)
        .join(User, User.id == Message.sender_id)
        .where(*conditions)
        .order_by(Message.created_at.desc(), Message.id.desc())
        .limit(limit)
    )
    # query is newest-first to fetch the latest page efficiently with
    # before_id, but the chat UI expects chronological (oldest-first) order.
    rows = list(reversed(result.all()))
    return [_to_message_read(message, sender_public_id) for message, sender_public_id in rows]


@router.post(
    "/conversations/{conversation_id}/messages",
    status_code=201,
    dependencies=[Depends(limit_messages)],
)
async def send_message(
    conversation_id: PathId,
    payload: MessageCreate,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
    hub: Hub = Depends(get_hub),
) -> MessageRead:
    conversation = await _require_conversation(session, conversation_id, current_user.id)
    if conversation.closed:
        raise HTTPException(status_code=409, detail="Conversation is closed")
    await _require_not_blocked(
        session, current_user.id, _other_participant_id(conversation, current_user.id)
    )
    await enforce(
        session,
        current_user.id,
        select(func.count()).select_from(Message).where(Message.conversation_id == conversation_id),
        settings.quota_messages_per_conversation,
        "This conversation is full",
        lock=False,
    )

    message = Message(
        conversation_id=conversation_id,
        sender_id=current_user.id,
        body=payload.body,
    )
    session.add(message)
    await session.commit()

    other_public_id = await session.scalar(
        select(User.public_id).where(
            User.id == _other_participant_id(conversation, current_user.id)
        )
    )
    buyer, seller = (
        (current_user.public_id, other_public_id)
        if conversation.buyer_id == current_user.id
        else (other_public_id, current_user.public_id)
    )
    remember_participants(conversation.id, buyer, seller)

    read = _to_message_read(message, current_user.public_id)
    # to both participants: the sender's other tabs need it too
    publish_to_users(
        hub, "message.created", (str(buyer), str(seller)), read.model_dump(mode="json")
    )
    return read
