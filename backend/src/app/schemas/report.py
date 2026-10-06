import uuid
from datetime import datetime
from typing import Annotated, Literal

from pydantic import BaseModel, BeforeValidator, StringConstraints, model_validator

from app.models.enums import ReportStatus
from app.schemas.limits import MAX_TARGET_ID_LENGTH, ReportReason
from app.schemas.listing import ListingRead
from app.schemas.review import ReviewRead
from app.schemas.user import PublicUser

ReportTargetKind = Literal["listing", "message", "user", "review"]


def _int_id_to_str(value: object) -> object:
    # message/review ids are ints everywhere else in the API (MessageRead.id,
    # ReviewRead.id), so a client may echo one back as a JSON number
    # bool is an int subclass
    if isinstance(value, int) and not isinstance(value, bool):
        return str(value)
    return value


TargetId = Annotated[
    str,
    BeforeValidator(_int_id_to_str),
    StringConstraints(min_length=1, max_length=MAX_TARGET_ID_LENGTH),
]


class ReportCreate(BaseModel):
    target_type: ReportTargetKind
    # listing/user targets carry a public_id (UUID); message/review targets
    # have no public_id and are addressed by their raw int id - both arrive
    # here as a string, like Notion's spec documents it.
    # (a JSON number is accepted too, see _int_id_to_str)
    target_id: TargetId
    reason: ReportReason


class ReportMessageTarget(BaseModel):
    # Messages have no public_id (never exposed anywhere else either -
    # MessageRead.id is the raw int), so the preview carries its own id.
    id: int
    conversation_id: int
    sender_id: uuid.UUID
    sender: PublicUser
    body: str
    created_at: datetime


class ReportRead(BaseModel):
    # Report rows have no public_id (same reasoning as messages/reviews),
    # but every id in the front's types is typed as `string` - stringify
    # here rather than pushing that coercion onto every caller.
    id: str
    reporter_id: uuid.UUID
    target_type: ReportTargetKind
    target_id: str
    reason: str
    status: ReportStatus
    created_at: datetime
    closed_at: datetime | None
    reporter: PublicUser
    # None when the target row no longer exists - reports.target_id is a
    # polymorphic reference with no FK, so it can dangle.
    target: ListingRead | ReportMessageTarget | PublicUser | ReviewRead | None = None


class ReportResolveRequest(BaseModel):
    action: Literal["delete_target", "block_user"]
    # Defaults to the report's own target when omitted - only needed to
    # sanction something other than what was originally reported.
    target_type: ReportTargetKind | None = None
    target_id: TargetId | None = None
    user_id: uuid.UUID | None = None

    @model_validator(mode="after")
    def _check_action_fields(self) -> ReportResolveRequest:
        if self.action == "block_user" and self.user_id is None:
            raise ValueError("user_id is required for the block_user action")
        if (self.target_type is None) != (self.target_id is None):
            raise ValueError("target_type and target_id must be provided together")
        return self


class ReportReopenRequest(BaseModel):
    action: Literal["unblock_user", "restore_target"] | None = None
    user_id: uuid.UUID | None = None

    @model_validator(mode="after")
    def _check_action_fields(self) -> ReportReopenRequest:
        if self.action == "unblock_user" and self.user_id is None:
            raise ValueError("user_id is required for the unblock_user action")
        return self


class ReportActionResponse(BaseModel):
    id: str
    status: ReportStatus
    closed_at: datetime | None
    message: str | None = None
