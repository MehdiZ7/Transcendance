from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    CHAR,
    BigInteger,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Identity,
    Integer,
    Text,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, TSVECTOR, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base
from app.models.catalog import Category, Location
from app.models.enums import ListingStatus, enum_check, enum_column
from app.models.users import User


class ListingCondition(Base):
    """Lookup table for listings.condition: new, like_new, good, fair,
    for_parts - editable without a migration."""

    __tablename__ = "listing_conditions"

    id: Mapped[str] = mapped_column(Text, primary_key=True)
    label: Mapped[str] = mapped_column(Text, nullable=False)


class Listing(Base):
    __tablename__ = "listings"
    __table_args__ = (
        CheckConstraint("price >= 0", name="price_non_negative"),
        enum_check("status", ListingStatus),
        CheckConstraint(
            "buyer_id IS NULL OR buyer_id <> seller_id", name="buyer_not_seller"
        ),
    )

    id: Mapped[int] = mapped_column(BigInteger, Identity(always=True), primary_key=True)
    public_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        nullable=False,
        unique=True,
        server_default=text("gen_random_uuid()"),
    )
    seller_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    buyer_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )
    category_id: Mapped[int | None] = mapped_column(
        ForeignKey("categories.id", ondelete="SET NULL"), index=True
    )
    title: Mapped[str] = mapped_column(Text, nullable=False)
    body: Mapped[str | None] = mapped_column(Text)
    price: Mapped[int] = mapped_column(BigInteger, nullable=False, server_default="0")
    currency: Mapped[str] = mapped_column(
        CHAR(3), nullable=False, server_default=text("'EUR'")
    )
    condition: Mapped[str | None] = mapped_column(ForeignKey("listing_conditions.id"))
    attributes: Mapped[dict] = mapped_column(
        JSONB, nullable=False, server_default=text("'{}'::jsonb")
    )
    location_id: Mapped[int | None] = mapped_column(
        ForeignKey("locations.id", ondelete="SET NULL"), index=True
    )
    status: Mapped[ListingStatus] = mapped_column(
        enum_column(ListingStatus),
        nullable=False,
        server_default=ListingStatus.DRAFT.value,
        index=True,
    )
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    cover_image_id: Mapped[int | None] = mapped_column(
        ForeignKey(
            "listing_images.id",
            ondelete="SET NULL",
            use_alter=True,
            name="fk_listings_cover_image",
        )
    )
    view_count: Mapped[int] = mapped_column(
        BigInteger, nullable=False, server_default="0"
    )
    search_vector: Mapped[str | None] = mapped_column(TSVECTOR)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )
    updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    seller: Mapped[User] = relationship(
        back_populates="listings", foreign_keys=[seller_id]
    )
    buyer: Mapped[User | None] = relationship(foreign_keys=[buyer_id])
    category: Mapped[Category | None] = relationship()
    location: Mapped[Location | None] = relationship()
    images: Mapped[list[ListingImage]] = relationship(
        back_populates="listing",
        cascade="all, delete-orphan",
        foreign_keys="ListingImage.listing_id",
    )


class ListingImage(Base):
    __tablename__ = "listing_images"

    id: Mapped[int] = mapped_column(BigInteger, Identity(always=True), primary_key=True)
    listing_id: Mapped[int] = mapped_column(
        ForeignKey("listings.id", ondelete="CASCADE"), nullable=False, index=True
    )
    storage_path: Mapped[str] = mapped_column(Text, nullable=False)
    position: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    width: Mapped[int | None] = mapped_column(Integer)
    height: Mapped[int | None] = mapped_column(Integer)
    phash: Mapped[int | None] = mapped_column(
        BigInteger,
        comment="64-bit perceptual hash (dHash/pHash) of the image, used to detect duplicate/scam reposts",
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )

    listing: Mapped[Listing] = relationship(
        back_populates="images", foreign_keys=[listing_id]
    )


class ListingFavorite(Base):
    __tablename__ = "listing_favorites"

    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    listing_id: Mapped[int] = mapped_column(
        ForeignKey("listings.id", ondelete="CASCADE"), primary_key=True, index=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )


class SavedSearch(Base):
    __tablename__ = "saved_searches"

    id: Mapped[int] = mapped_column(BigInteger, Identity(always=True), primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    search_name: Mapped[str] = mapped_column(Text, nullable=False)
    criteria: Mapped[dict] = mapped_column(
        JSONB, nullable=False, server_default=text("'{}'::jsonb")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )
