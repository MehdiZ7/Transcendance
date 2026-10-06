import uuid
from datetime import datetime

from pydantic import BaseModel, Field, computed_field

from app.schemas.limits import AvatarPath, Bio, DbId, DisplayName


class PublicUser(BaseModel):
    public_id: uuid.UUID
    display_name: str
    avatar_path: str | None
    bio: str | None
    rating: float
    rating_count: int
    is_active: bool

    # Front's User types expect an `id` field (used for e.g. message
    # sender_id comparisons, React keys) but the internal bigint PK is never
    # exposed - mirror public_id instead, same pattern as ListingRead.id.
    @computed_field
    @property
    def id(self) -> uuid.UUID:
        return self.public_id


class UserProfile(PublicUser):
    role: str
    created_at: datetime


class OtherUserProfile(UserProfile):
    """GET /users/{public_id}: the profile as the caller sees it."""

    # The person behind this profile blocked the caller. One way only, on
    # purpose: the caller's own blocks are GET /users/me/blocks. Always False
    # without a session and on one's own profile.
    has_blocked_me: bool = False


class MeProfile(UserProfile):
    email: str
    location_id: int | None
    friends_count: int
    listings_count: int
    reviews_count: int
    has_password: bool


class MeUpdate(BaseModel):
    display_name: DisplayName | None = None
    bio: Bio | None = None
    avatar_path: AvatarPath | None = None
    location_id: DbId | None = None


class MeUpdated(BaseModel):
    public_id: uuid.UUID
    display_name: str
    bio: str | None
    avatar_path: str | None
    location_id: int | None
    updated_at: datetime


class AdminUserRead(BaseModel):
    """A row of the admin user list. No email: personal data the list does not need."""

    public_id: uuid.UUID
    display_name: str
    role: str
    is_active: bool
    created_at: datetime
    deleted_at: datetime | None


class RoleUpdate(BaseModel):
    role: str = Field(min_length=1, max_length=50)
