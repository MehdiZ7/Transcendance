"""Per-user quotas: how many rows one user can create.

The size of a request is bounded by app/schemas/limits.py; this bounds how many
requests are worth a row. The values are `quota_*` in app/core/config.py.

Two kinds, answered differently so the client can tell them apart:

- a total (active listings, friends, favorites...): 409, the user has to delete
  something first;
- a window (listings, conversations, reports per 24 h): 429, it comes back by
  itself.

The count and the insert are not atomic, so two parallel requests could both
see room for one more. `enforce` first locks the user's row with FOR NO KEY
UPDATE, which makes a user's own creations queue up. Not FOR UPDATE: every
insert that references a user checks its foreign key with FOR KEY SHARE on
that row, which FOR UPDATE blocks, so two users acting on each other at once
(friend requests, blocks, a conversation on each other's listing) would
deadlock. Use `lock=False` where the cap is coarse and the lock would only
slow every request down (messages per conversation).
"""

from datetime import UTC, datetime, timedelta

from fastapi import HTTPException
from sqlalchemy import Select, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import User

WINDOW = timedelta(hours=24)


def since_window() -> datetime:
    """Start of the 24 h window the `*_per_day` quotas count over."""
    return datetime.now(UTC) - WINDOW


async def enforce(
    session: AsyncSession,
    user_id: int,
    count: Select,
    limit: int,
    detail: str,
    *,
    status_code: int = 409,
    lock: bool = True,
) -> None:
    """Raise `status_code` if `count` (a `select(func.count())...`) already
    reaches `limit`. Call it before adding the row, in the same transaction."""
    if lock:
        await session.execute(
            select(User.id).where(User.id == user_id).with_for_update(key_share=True)
        )
    if (await session.scalar(count) or 0) >= limit:
        raise HTTPException(status_code=status_code, detail=detail)
