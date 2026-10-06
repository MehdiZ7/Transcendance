from enum import StrEnum

from sqlalchemy import CheckConstraint
from sqlalchemy import Enum as SAEnum


class DataType(StrEnum):
    INT = "int"
    DEC = "dec"
    BOOL = "bool"
    ENUM = "enum"
    TEXT = "text"
    DATE = "date"


class FriendStatus(StrEnum):
    PENDING = "pending"
    ACCEPTED = "accepted"
    DECLINED = "declined"
    BLOCKED = "blocked"


class ListingStatus(StrEnum):
    DRAFT = "draft"
    ACTIVE = "active"
    SOLD = "sold"
    EXPIRED = "expired"
    ARCHIVED = "archived"
    DELETED = "deleted"


class ReportStatus(StrEnum):
    OPEN = "open"
    IN_PROGRESS = "in_progress"
    RESOLVED = "resolved"
    CLOSED = "closed"


def enum_column(enum_cls: type[StrEnum], *, length: int = 32) -> SAEnum:
    """String-backed enum column: stores the lowercase *values* (what the front expects), loads real enum members
    No native PG enum, no implicit CHECK
    pair with enum_check() so the constraint is explicit and alembic-visible
    """
    return SAEnum(
        enum_cls,
        native_enum=False,
        create_constraint=False,
        length=length,
        values_callable=lambda e: [m.value for m in e],
    )


def enum_check(column: str, enum_cls: type[StrEnum]) -> CheckConstraint:
    """CHECK (<column> IN (...)) generated from the enum -> ck_<table>_<column>_valid."""
    values = ", ".join(f"'{m.value}'" for m in enum_cls)
    return CheckConstraint(f"{column} IN ({values})", name=f"{column}_valid")
