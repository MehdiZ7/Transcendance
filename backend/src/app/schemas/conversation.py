import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel

from app.models.enums import ListingStatus
from app.schemas.limits import MessageBody
from app.schemas.user import PublicUser


class ConversationCreate(BaseModel):
    listing_id: uuid.UUID


class MessageRead(BaseModel):
    id: int
    conversation_id: int
    sender_id: uuid.UUID
    body: str
    created_at: datetime
    edited_at: datetime | None
    deleted_at: datetime | None


class MessageCreate(BaseModel):
    body: MessageBody


class ConversationSummary(BaseModel):
    # Lets the front merge this with FriendConversationSummary into one
    # inbox without guessing the thread's kind from field presence.
    type: Literal["listing"] = "listing"
    id: int
    listing_id: int
    listing_public_id: uuid.UUID
    listing_title: str
    listing_cover_image: str | None
    other_participant: PublicUser
    last_message: MessageRead | None
    # TODO: no read-tracking column exists on conversations yet - always 0
    # until one is added.
    unread_count: int = 0
    is_closed: bool
    updated_at: datetime
    listing_status: ListingStatus
    listing_seller_id: uuid.UUID
    # Set only on the conversation the listing was sold through
    # the same rule POST /reviews enforces
    listing_buyer_id: uuid.UUID | None
    # Whether the buyer reviewed the seller here
    has_reviewed: bool


class MarkSoldResponse(BaseModel):
    id: int
    listing_id: int
    listing_public_id: uuid.UUID
    listing_title: str
    listing_status: ListingStatus
    listing_seller_id: uuid.UUID
    listing_buyer_id: uuid.UUID
    has_reviewed: bool
    message: str | None = None
