from __future__ import annotations

from sqlalchemy import (
    BigInteger,
    Boolean,
    ForeignKey,
    Identity,
    SmallInteger,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base
from app.models.enums import DataType, enum_check, enum_column


class Category(Base):
    __tablename__ = "categories"

    id: Mapped[int] = mapped_column(BigInteger, Identity(always=True), primary_key=True)
    parent_id: Mapped[int | None] = mapped_column(
        ForeignKey("categories.id", ondelete="SET NULL"), index=True
    )
    depth: Mapped[int] = mapped_column(SmallInteger, nullable=False, server_default="0")
    category_name: Mapped[str] = mapped_column(Text, nullable=False)
    is_leaf: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("true")
    )

    attributes: Mapped[list[CategoryAttribute]] = relationship(
        back_populates="category", cascade="all, delete-orphan"
    )


class CategoryAttribute(Base):
    __tablename__ = "category_attributes"
    __table_args__ = (
        UniqueConstraint("category_id", "key"),
        enum_check("data_type", DataType),
    )

    id: Mapped[int] = mapped_column(BigInteger, Identity(always=True), primary_key=True)
    category_id: Mapped[int] = mapped_column(
        ForeignKey("categories.id", ondelete="CASCADE"), nullable=False
    )
    key: Mapped[str] = mapped_column(Text, nullable=False)
    data_type: Mapped[DataType] = mapped_column(enum_column(DataType), nullable=False)
    unit: Mapped[str | None] = mapped_column(Text)
    is_required: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("false")
    )
    is_filterable: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("false")
    )
    options: Mapped[dict | None] = mapped_column(JSONB)

    category: Mapped[Category] = relationship(back_populates="attributes")


class Location(Base):
    __tablename__ = "locations"

    id: Mapped[int] = mapped_column(BigInteger, Identity(always=True), primary_key=True)
    location: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
