import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, computed_field

from app.models.enums import ListingStatus
from app.schemas.catalog import CategoryRead, LocationRead
from app.schemas.limits import (
    MAX_IMAGES_PER_LISTING,
    Attributes,
    Currency,
    DbId,
    ImageUrl,
    ListingBody,
    ListingTitle,
    Price,
)
from app.schemas.user import PublicUser

ListingCondition = Literal["new", "like_new", "good", "fair", "for_parts"]


class ListingRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    public_id: uuid.UUID
    title: str
    body: str | None
    price: int
    currency: str
    condition: str | None
    status: ListingStatus
    view_count: int
    created_at: datetime
    updated_at: datetime | None
    # Despite the name (kept for front compat), this holds the cover image's
    # storage_path - not the internal listing_images.id it's a FK to.
    cover_image_id: str | None = None
    favorites_count: int = 0
    is_favorited: bool = False
    seller: PublicUser
    category: CategoryRead | None
    location: LocationRead | None

    # Front's Listing type expects an `id` field (used as React key etc.) but
    # the internal bigint PK is never exposed - mirror public_id instead of
    # reading it from the ORM object.
    @computed_field
    @property
    def id(self) -> uuid.UUID:
        return self.public_id


class ListingImageRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    storage_path: str
    position: int
    width: int | None
    height: int | None
    created_at: datetime


class ListingDetail(BaseModel):
    public_id: uuid.UUID
    title: str
    body: str | None
    price: int
    currency: str
    condition: str | None
    attributes: dict
    status: ListingStatus
    view_count: int
    favorites_count: int
    is_favorited: bool = False
    published_at: datetime | None
    expires_at: datetime | None
    created_at: datetime
    updated_at: datetime | None
    seller: PublicUser
    category: CategoryRead | None
    location: LocationRead | None
    images: list[ListingImageRead]
    # Same as ListingRead.cover_image_id: the cover image's storage_path.
    cover_image_id: str | None = None

    @computed_field
    @property
    def id(self) -> uuid.UUID:
        return self.public_id


class ListingCreate(BaseModel):
    title: ListingTitle
    body: ListingBody
    price: Price
    currency: Currency = "EUR"
    category_id: DbId
    location_id: DbId
    condition: ListingCondition | None = None
    attributes: Attributes = Field(default_factory=dict)
    image_urls: list[ImageUrl] = Field(default_factory=list, max_length=MAX_IMAGES_PER_LISTING)


class FavoriteResponse(BaseModel):
    is_favorited: bool
    favorites_count: int
    message: str | None = None
