from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    BigInteger,
    DateTime,
    ForeignKey,
    Identity,
    Index,
    Text,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base
from app.models.enums import ReportStatus, enum_check, enum_column


class ReportTargetType(Base):
    """Lookup table for reports.target_type: listing, message, user, review -
    editable without a migration."""

    __tablename__ = "report_target_types"

    id: Mapped[str] = mapped_column(Text, primary_key=True)
    label: Mapped[str] = mapped_column(Text, nullable=False)


class Report(Base):
    __tablename__ = "reports"
    __table_args__ = (
        enum_check("status", ReportStatus),
        Index("ix_reports_target", "target_type", "target_id"),
    )

    id: Mapped[int] = mapped_column(BigInteger, Identity(always=True), primary_key=True)
    reporter_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    target_type: Mapped[str] = mapped_column(
        ForeignKey("report_target_types.id"), nullable=False
    )
    target_id: Mapped[int] = mapped_column(
        BigInteger,
        nullable=False,
        comment="Polymorphic reference: id of the row in the table named by target_type (no FK enforced)",
    )
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[ReportStatus] = mapped_column(
        enum_column(ReportStatus),
        nullable=False,
        server_default=ReportStatus.OPEN.value,
        index=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
