"""Admin-only user management: list users with their role, change a role,
delete a user. Every route needs the admin role (403 otherwise)."""

import logging
import shutil
import uuid
from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy import delete, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.concurrency import run_in_threadpool

from app.core.db import get_session
from app.core.realtime.hub import Hub
from app.core.security import require_admin
from app.core.uploads import owner_dir
from app.models import Review, Role, User
from app.realtime import get_hub
from app.schemas.limits import NoNul
from app.schemas.pagination import PaginatedResponse
from app.schemas.user import AdminUserRead, RoleUpdate

logger = logging.getLogger(__name__)

router = APIRouter()


def _to_admin_user(user: User) -> AdminUserRead:
    return AdminUserRead(
        public_id=user.public_id,
        display_name=user.display_name,
        role=user.role,
        is_active=user.is_active,
        created_at=user.created_at,
        deleted_at=user.deleted_at,
    )


@router.get("/users")
async def list_users(
    page: int = Query(1, ge=1, le=10_000),
    limit: int = Query(30, ge=1, le=100),
    q: Annotated[str | None, Query(max_length=100), NoNul] = None,
    role: Annotated[str | None, Query(max_length=50), NoNul] = None,
    _admin: User = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
) -> PaginatedResponse[AdminUserRead]:
    """Every account, newest first, with its role. Suspended (is_active false)
    and soft-deleted (deleted_at set) accounts are included on purpose: the
    admin is the one who has to see and deal with them. `q` matches the
    display name, `role` filters on an exact role."""
    conditions = []
    if q:
        escaped = q.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        conditions.append(User.display_name.ilike(f"%{escaped}%", escape="\\"))
    if role:
        conditions.append(User.role == role)

    total = await session.scalar(select(func.count()).select_from(User).where(*conditions)) or 0
    users = await session.scalars(
        select(User)
        .where(*conditions)
        .order_by(User.created_at.desc(), User.id.desc())
        .offset((page - 1) * limit)
        .limit(limit)
    )
    return PaginatedResponse(
        data=[_to_admin_user(user) for user in users],
        total=total,
        page=page,
        limit=limit,
        total_pages=-(-total // limit),
    )


@router.patch("/users/{public_id}/role")
async def change_user_role(
    public_id: uuid.UUID,
    payload: RoleUpdate,
    admin: User = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
) -> AdminUserRead:
    """The role is read from the database on every request (the JWT does not
    carry it), so the change applies at once, without a new login. Nobody can
    change their own role: that is what keeps at least one admin."""
    target = await session.scalar(
        select(User).where(User.public_id == public_id, User.deleted_at.is_(None))
    )
    if target is None:
        raise HTTPException(status_code=404, detail="User not found")
    if target.id == admin.id:
        raise HTTPException(status_code=400, detail="Cannot change your own role")
    # users.role is a foreign key into the roles table (editable without a migration)
    if await session.scalar(select(Role.id).where(Role.id == payload.role)) is None:
        raise HTTPException(status_code=422, detail="Unknown role")

    if target.role != payload.role:
        target.role = payload.role
        target.updated_at = datetime.now(UTC)
        await session.commit()
    return _to_admin_user(target)


@router.delete("/users/{public_id}", status_code=204)
async def delete_user(
    public_id: uuid.UUID,
    admin: User = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
    hub: Hub = Depends(get_hub),
) -> Response:
    """A real, irreversible delete of the users row. The database cascades to
    everything that references it (ON DELETE CASCADE): their listings with the
    conversations, messages and favorites on them, their conversations as a
    buyer, the reviews they wrote and received, friendships and direct
    messages, blocks, favorites, reports they filed and OAuth accounts, and the
    images they uploaded are removed from the disk.
    Listings they bought from others stay, with buyer_id set to NULL.

    What the cascade cannot do is done first: the reviews they wrote take their
    rating out of the users.rating / rating_count counters of the people they
    reviewed, as moderation does when it deletes a review. A soft-deleted
    account can be deleted too. Nobody deletes themselves."""
    target = await session.scalar(select(User).where(User.public_id == public_id))
    if target is None:
        raise HTTPException(status_code=404, detail="User not found")
    if target.id == admin.id:
        raise HTTPException(status_code=400, detail="Cannot delete yourself")

    written = await session.execute(
        select(Review.subject_id, func.sum(Review.rating), func.count())
        .where(Review.author_id == target.id, Review.deleted_at.is_(None))
        .group_by(Review.subject_id)
    )
    for subject_id, rating_sum, review_count in written.all():
        await session.execute(
            update(User)
            .where(User.id == subject_id)
            .values(rating=User.rating - int(rating_sum), rating_count=User.rating_count - review_count)
        )

    await session.execute(delete(User).where(User.id == target.id))
    await session.commit()

    # The session is a stateless JWT for a user that no longer exists: REST now
    # answers 401, the realtime socket has to follow
    hub.registry.close_principal(str(public_id))
    # their uploaded images go with them (the rows that pointed at them just went)
    try:
        await run_in_threadpool(shutil.rmtree, owner_dir(public_id))
    except FileNotFoundError:
        pass  # nothing was ever uploaded
    except OSError:
        logger.exception("could not remove uploads for %s", public_id)
    return Response(status_code=204)
