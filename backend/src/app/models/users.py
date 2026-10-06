from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Identity,
    Integer,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import CITEXT, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base
from app.models.enums import FriendStatus, enum_check, enum_column

if TYPE_CHECKING:
    from app.models.listings import Listing


class Role(Base):
    """Lookup table for users.role: user, moderator, admin - editable without a migration."""

    __tablename__ = "roles"

    id: Mapped[str] = mapped_column(Text, primary_key=True)
    label: Mapped[str] = mapped_column(Text, nullable=False)


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(BigInteger, Identity(always=True), primary_key=True)
    public_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        nullable=False,
        unique=True,
        server_default=text("gen_random_uuid()"),
    )
    email: Mapped[str] = mapped_column(CITEXT, nullable=False, unique=True)
    password_hash: Mapped[str | None] = mapped_column(
        Text, comment="NULL for OAuth-only accounts"
    )
    display_name: Mapped[str] = mapped_column(CITEXT, nullable=False)
    role: Mapped[str] = mapped_column(
        ForeignKey("roles.id"), nullable=False, server_default=text("'user'")
    )
    bio: Mapped[str | None] = mapped_column(Text)
    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("true")
    )
    avatar_path: Mapped[str | None] = mapped_column(Text)
    location_id: Mapped[int | None] = mapped_column(
        ForeignKey("locations.id", ondelete="SET NULL"), index=True
    )
    locale: Mapped[str] = mapped_column(
        Text, nullable=False, server_default=text("'fr'")
    )
    totp_secret_encrypted: Mapped[str | None] = mapped_column(
        Text, comment="NULL until the user enrolls in 2FA"
    )
    totp_enabled: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("false")
    )
    rating: Mapped[int] = mapped_column(
        BigInteger,
        nullable=False,
        server_default="0",
        comment="Sum of review ratings received",
    )
    rating_count: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default="0"
    )
    email_verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )

    oauth_accounts: Mapped[list[OAuthAccount]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )
    listings: Mapped[list[Listing]] = relationship(
        back_populates="seller", foreign_keys="Listing.seller_id"
    )


class OAuthAccount(Base):
    __tablename__ = "oauth_accounts"
    __table_args__ = (UniqueConstraint("provider", "provider_account_id"),)

    id: Mapped[int] = mapped_column(BigInteger, Identity(always=True), primary_key=True)
    provider: Mapped[str] = mapped_column(Text, nullable=False)
    provider_account_id: Mapped[str] = mapped_column(Text, nullable=False)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )

    user: Mapped[User] = relationship(back_populates="oauth_accounts")


class UserBlock(Base):
    __tablename__ = "user_blocks"
    __table_args__ = (
        CheckConstraint("user_blocking <> user_blocked", name="no_self_block"),
    )

    user_blocking: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    user_blocked: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), primary_key=True, index=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )


class Friend(Base):
    __tablename__ = "friends"
    __table_args__ = (
        CheckConstraint("requester_id <> address_id", name="no_self_friend"),
        UniqueConstraint("requester_id", "address_id"),
        enum_check("status", FriendStatus),
    )

    id: Mapped[int] = mapped_column(BigInteger, Identity(always=True), primary_key=True)
    requester_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    address_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    status: Mapped[FriendStatus] = mapped_column(
        enum_column(FriendStatus),
        nullable=False,
        server_default=FriendStatus.PENDING.value,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )
    responded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class FriendMessage(Base):
    """Direct chat between friends"""

    __tablename__ = "friends_messages"

    id: Mapped[int] = mapped_column(BigInteger, Identity(always=True), primary_key=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("now()"),
    )
    conversation_id: Mapped[int] = mapped_column(
        ForeignKey("friends.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    sender_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    body: Mapped[str] = mapped_column(Text, nullable=False)
    edited_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
