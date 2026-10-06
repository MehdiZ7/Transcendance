import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel

from app.models.enums import FriendStatus
from app.schemas.limits import MessageBody
from app.schemas.user import PublicUser


class FriendRequestCreate(BaseModel):
    user_id: uuid.UUID


class FriendMessageRead(BaseModel):
    id: int
    friend_id: int
    sender_id: uuid.UUID
    body: str
    created_at: datetime
    edited_at: datetime | None
    deleted_at: datetime | None


class FriendMessageCreate(BaseModel):
    body: MessageBody


class FriendConversationSummary(BaseModel):
    # Lets the front merge this with ConversationSummary into one inbox
    # without guessing the thread's kind from field presence.
    type: Literal["friend"] = "friend"
    friend_id: int
    other_participant: PublicUser
    last_message: FriendMessageRead | None
    # TODO: no read-tracking column exists on friends_messages yet - always
    # 0 until one is added.
    unread_count: int = 0
    updated_at: datetime

class FriendRead(BaseModel):
    # friends.id has no public_id (never exposed anywhere else either), but
    # every id in the front's types is a string - stringify here rather
    # than pushing that coercion onto the caller.
    id: str
    requester_id: uuid.UUID
    address_id: uuid.UUID
    # Convenient alias the front's Friend type carries alongside address_id
    # for the same value - same column, read twice.
    addressee_id: uuid.UUID
    status: FriendStatus
    created_at: datetime
    responded_at: datetime | None
    requester: PublicUser
    addressee: PublicUser | None = None
