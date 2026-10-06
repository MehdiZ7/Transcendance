import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from app.core.analytics_bus import analytics_bus
from app.core.config import settings
from app.core.db import get_session
from app.core.quotas import enforce, since_window
from app.core.ratelimit import limit_reports
from app.core.realtime.hub import Hub
from app.core.security import can_sanction, get_current_moderator, get_current_user
from app.core.serializers import to_listing_read, to_public_user
from app.core.uploads import own_upload_missing
from app.models import (
    Listing,
    ListingFavorite,
    ListingImage,
    Message,
    Report,
    Review,
    User,
)
from app.models.enums import ListingStatus, ReportStatus
from app.realtime import get_hub
from app.schemas.limits import PathId
from app.schemas.listing import ListingRead
from app.schemas.report import (
    ReportActionResponse,
    ReportCreate,
    ReportMessageTarget,
    ReportRead,
    ReportReopenRequest,
    ReportResolveRequest,
    ReportTargetKind,
)
from app.schemas.review import ReviewRead

router = APIRouter()

_LISTING_OPTIONS = (
    joinedload(Listing.seller),
    joinedload(Listing.category),
    joinedload(Listing.location),
)


async def _load_listing(session: AsyncSession, **where: object) -> Listing | None:
    return await session.scalar(select(Listing).options(*_LISTING_OPTIONS).filter_by(**where))


async def _listing_target(session: AsyncSession, listing: Listing) -> ListingRead:
    favorites_count = await session.scalar(
        select(func.count()).select_from(ListingFavorite).where(ListingFavorite.listing_id == listing.id)
    )
    cover_image_path = None
    if listing.cover_image_id is not None:
        cover_image_path = await session.scalar(
            select(ListingImage.storage_path).where(ListingImage.id == listing.cover_image_id)
        )
    # is_favorited isn't meaningful for a moderation preview (not relative to
    # any particular viewer) - always False here.
    return to_listing_read(listing, cover_image_path, favorites_count or 0, False)


async def _message_target(session: AsyncSession, message: Message) -> ReportMessageTarget:
    sender = await session.get(User, message.sender_id)
    return ReportMessageTarget(
        id=message.id,
        conversation_id=message.conversation_id,
        sender_id=sender.public_id,
        sender=to_public_user(sender),
        body=message.body,
        created_at=message.created_at,
    )


async def _review_target(session: AsyncSession, review: Review) -> ReviewRead:
    author = await session.get(User, review.author_id)
    return ReviewRead(
        id=review.id,
        conversation_id=review.conversation_id,
        rating=review.rating,
        body=review.body,
        created_at=review.created_at,
        author=to_public_user(author),
    )


async def _resolve_target(
    session: AsyncSession, target_type: ReportTargetKind, target_id: str
) -> tuple[int, str, object]:
    """Turn the client-facing target id (a UUID public_id for listing/user,
    a raw int for message/review - reports.target_id is a polymorphic
    reference with no FK enforced) into the target's internal id, its
    normalized public-facing id, and a full preview object for the
    response's `target`. Raises 404 if the target doesn't exist."""
    if target_type == "listing":
        try:
            public_id = uuid.UUID(target_id)
        except ValueError:
            raise HTTPException(status_code=404, detail="Report target not found") from None
        listing = await _load_listing(session, public_id=public_id)
        if listing is None or listing.status == ListingStatus.DELETED:
            # Same 404 either way - don't reveal whether it never existed or
            # was already removed, and nothing is actionable on it anyway.
            raise HTTPException(status_code=404, detail="Report target not found")
        return listing.id, str(listing.public_id), await _listing_target(session, listing)

    if target_type == "user":
        try:
            public_id = uuid.UUID(target_id)
        except ValueError:
            raise HTTPException(status_code=404, detail="Report target not found") from None
        user = await session.scalar(select(User).where(User.public_id == public_id))
        if user is None or user.deleted_at is not None:
            raise HTTPException(status_code=404, detail="Report target not found")
        return user.id, str(user.public_id), to_public_user(user)

    try:
        raw_id = int(target_id)
    except ValueError:
        raise HTTPException(status_code=404, detail="Report target not found") from None

    if target_type == "message":
        message = await session.get(Message, raw_id)
        if message is None or message.deleted_at is not None:
            raise HTTPException(status_code=404, detail="Report target not found")
        return message.id, str(message.id), await _message_target(session, message)

    review = await session.get(Review, raw_id)
    if review is None or review.deleted_at is not None:
        raise HTTPException(status_code=404, detail="Report target not found")
    return review.id, str(review.id), await _review_target(session, review)


async def _load_target_by_internal_id(
    session: AsyncSession, target_type: ReportTargetKind, internal_id: int
) -> tuple[str, object | None]:
    """Reverse of _resolve_target: given the internal id stored on the
    report, rebuild the public-facing target_id and a preview object.
    Returns (str(internal_id), None) if the target row no longer exists."""
    if target_type == "listing":
        listing = await _load_listing(session, id=internal_id)
        if listing is None:
            return str(internal_id), None
        return str(listing.public_id), await _listing_target(session, listing)

    if target_type == "user":
        user = await session.get(User, internal_id)
        if user is None:
            return str(internal_id), None
        return str(user.public_id), to_public_user(user)

    if target_type == "message":
        message = await session.get(Message, internal_id)
        if message is None:
            return str(internal_id), None
        return str(message.id), await _message_target(session, message)

    review = await session.get(Review, internal_id)
    if review is None:
        return str(internal_id), None
    return str(review.id), await _review_target(session, review)


async def _require_report(session: AsyncSession, report_id: int) -> Report:
    # with_for_update: resolve/reject/reopen all read-then-write status -
    # without a lock, two concurrent moderators could both pass the status
    # check before either commits and both mutate the same report.
    report = await session.scalar(
        select(Report).where(Report.id == report_id).with_for_update()
    )
    if report is None:
        raise HTTPException(status_code=404, detail="Report not found")
    return report


async def _close_sibling_reports(
    session: AsyncSession, target_type: ReportTargetKind, target_id: int, exclude_report_id: int
) -> None:
    """Once a report against (target_type, target_id) is actually acted on
    (delete_target/block_user, not reject), every other open/in_progress
    report against that same target is moot - close them too."""
    await session.execute(
        update(Report)
        .where(
            Report.target_type == target_type,
            Report.target_id == target_id,
            Report.status.in_((ReportStatus.OPEN, ReportStatus.IN_PROGRESS)),
            Report.id != exclude_report_id,
        )
        .values(status=ReportStatus.RESOLVED, closed_at=datetime.now(UTC))
    )


async def _delete_target(
    session: AsyncSession,
    target_type: ReportTargetKind,
    internal_id: int,
    actor: User,
) -> User | None:
    """Soft-remove the target. Returns the user removed, if the target was a
    user, so the caller can close their sockets once committed."""
    now = datetime.now(UTC)
    if target_type == "listing":
        listing = await session.get(Listing, internal_id)
        if listing is not None:
            listing.status = ListingStatus.DELETED
            listing.deleted_at = now
    elif target_type == "user":
        user = await session.get(User, internal_id)
        if user is not None:
            if user.id == actor.id:
                raise HTTPException(status_code=400, detail="Cannot remove yourself")
            if not can_sanction(actor, user):
                raise HTTPException(
                    status_code=403, detail="Insufficient role to remove this user"
                )
            user.deleted_at = now
            user.is_active = False
            return user
    elif target_type == "message":
        message = await session.get(Message, internal_id)
        if message is not None:
            message.deleted_at = now
    else:
        review = await session.get(Review, internal_id)
        # Guard against double-decrementing the subject's rating if this
        # report is somehow resolved twice against the same review.
        if review is not None and review.deleted_at is None:
            subject = await session.get(User, review.subject_id)
            if subject is not None:
                subject.rating -= review.rating
                subject.rating_count -= 1
            review.deleted_at = now


async def _restore_target(
    session: AsyncSession, target_type: ReportTargetKind, internal_id: int
) -> None:
    """Reverse of _delete_target. No-op if the target isn't currently
    removed (e.g. reopening a report that was resolved via block_user)."""
    if target_type == "listing":
        listing = await session.get(Listing, internal_id)
        if listing is not None and listing.status == ListingStatus.DELETED:
            # No record of the pre-delete status (SOLD/ARCHIVED/...) -
            # ACTIVE is the only sensible default to come back to.
            listing.status = ListingStatus.ACTIVE
            listing.deleted_at = None

            # The seller may have deleted this listing themselves - and its
            # images with it - independently of this report. Drop any image
            # row whose file is actually gone, rather than bring the listing
            # back with broken photos.
            images = await session.scalars(
                select(ListingImage).where(ListingImage.listing_id == listing.id)
            )
            for image in images:
                if own_upload_missing(image.storage_path):
                    await session.delete(image)
    elif target_type == "user":
        user = await session.get(User, internal_id)
        if user is not None and user.deleted_at is not None:
            user.deleted_at = None
            user.is_active = True
    elif target_type == "message":
        message = await session.get(Message, internal_id)
        if message is not None and message.deleted_at is not None:
            message.deleted_at = None
    else:
        review = await session.get(Review, internal_id)
        if review is not None and review.deleted_at is not None:
            subject = await session.get(User, review.subject_id)
            if subject is not None:
                subject.rating += review.rating
                subject.rating_count += 1
            review.deleted_at = None


@router.post("/reports", status_code=201, dependencies=[Depends(limit_reports)])
async def create_report(
    payload: ReportCreate,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> ReportRead:
    internal_id, target_id_str, target = await _resolve_target(
        session, payload.target_type, payload.target_id
    )
    if payload.target_type == "user" and internal_id == current_user.id:
        raise HTTPException(status_code=400, detail="Cannot report yourself")

    existing = await session.scalar(
        select(Report.id).where(
            Report.reporter_id == current_user.id,
            Report.target_type == payload.target_type,
            Report.target_id == internal_id,
            Report.status.in_((ReportStatus.OPEN, ReportStatus.IN_PROGRESS)),
        )
    )
    if existing is not None:
        raise HTTPException(
            status_code=409, detail="You already have an open report on this target"
        )

    await enforce(
        session,
        current_user.id,
        select(func.count()).select_from(Report).where(
            Report.reporter_id == current_user.id, Report.created_at > since_window()
        ),
        settings.quota_reports_per_day,
        "Too many reports today, try again later",
        status_code=429,
    )

    report = Report(
        reporter_id=current_user.id,
        target_type=payload.target_type,
        target_id=internal_id,
        reason=payload.reason,
    )
    session.add(report)
    await session.commit()
    analytics_bus.publish("report.created")

    return ReportRead(
        id=str(report.id),
        reporter_id=current_user.public_id,
        target_type=payload.target_type,
        target_id=target_id_str,
        reason=report.reason,
        status=report.status,
        created_at=report.created_at,
        closed_at=report.closed_at,
        reporter=to_public_user(current_user),
        target=target,
    )


@router.get("/reports")
async def list_reports(
    status: ReportStatus | None = None,
    target_type: ReportTargetKind | None = None,
    current_user: User = Depends(get_current_moderator),
    session: AsyncSession = Depends(get_session),
) -> list[ReportRead]:
    # Not paginated: the front builds its queues, their counters and the
    # history from this one list, and a page would silently hide the oldest
    # open reports - the ones that have waited longest.
    query = select(Report).order_by(Report.created_at.desc())
    if status is not None:
        query = query.where(Report.status == status)
    if target_type is not None:
        query = query.where(Report.target_type == target_type)

    reports = (await session.scalars(query)).all()

    result: list[ReportRead] = []
    for report in reports:
        reporter = await session.get(User, report.reporter_id)
        if reporter is None:
            continue
        target_id_str, target = await _load_target_by_internal_id(
            session, report.target_type, report.target_id
        )
        result.append(
            ReportRead(
                id=str(report.id),
                reporter_id=reporter.public_id,
                target_type=report.target_type,
                target_id=target_id_str,
                reason=report.reason,
                status=report.status,
                created_at=report.created_at,
                closed_at=report.closed_at,
                reporter=to_public_user(reporter),
                target=target,
            )
        )
    return result


@router.post("/reports/{report_id}/resolve")
async def resolve_report(
    report_id: PathId,
    payload: ReportResolveRequest,
    current_user: User = Depends(get_current_moderator),
    session: AsyncSession = Depends(get_session),
    hub: Hub = Depends(get_hub),
) -> ReportActionResponse:
    report = await _require_report(session, report_id)
    if report.status in (ReportStatus.RESOLVED, ReportStatus.CLOSED):
        raise HTTPException(status_code=409, detail="Report already closed")

    suspended: User | None = None
    if payload.action == "delete_target":
        target_type = payload.target_type or report.target_type
        internal_id = report.target_id
        if payload.target_id is not None:
            internal_id, _, _ = await _resolve_target(session, target_type, payload.target_id)
        suspended = await _delete_target(session, target_type, internal_id, current_user)
        message = "Target removed"
    else:
        user = await session.scalar(select(User).where(User.public_id == payload.user_id))
        if user is None:
            raise HTTPException(status_code=404, detail="User not found")
        if user.id == current_user.id:
            raise HTTPException(status_code=400, detail="Cannot suspend yourself")
        if not can_sanction(current_user, user):
            raise HTTPException(
                status_code=403, detail="Insufficient role to suspend this user"
            )
        user.is_active = False
        suspended = user
        message = "User suspended"

    await _close_sibling_reports(session, report.target_type, report.target_id, report.id)

    report.status = ReportStatus.RESOLVED
    report.closed_at = datetime.now(UTC)
    await session.commit()
    analytics_bus.publish("report.resolved")
    if suspended is not None:
        # REST refuses them from now on: the realtime socket must follow
        hub.registry.close_principal(str(suspended.public_id))

    return ReportActionResponse(
        id=str(report.id), status=report.status, closed_at=report.closed_at, message=message
    )


@router.post("/reports/{report_id}/reject")
async def reject_report(
    report_id: PathId,
    current_user: User = Depends(get_current_moderator),
    session: AsyncSession = Depends(get_session),
) -> ReportActionResponse:
    report = await _require_report(session, report_id)
    if report.status in (ReportStatus.RESOLVED, ReportStatus.CLOSED):
        raise HTTPException(status_code=409, detail="Report already closed")

    report.status = ReportStatus.CLOSED
    report.closed_at = datetime.now(UTC)
    await session.commit()
    analytics_bus.publish("report.rejected")

    return ReportActionResponse(
        id=str(report.id),
        status=report.status,
        closed_at=report.closed_at,
        message="Report dismissed",
    )


@router.post("/reports/{report_id}/reopen")
async def reopen_report(
    report_id: PathId,
    payload: ReportReopenRequest | None = None,
    current_user: User = Depends(get_current_moderator),
    session: AsyncSession = Depends(get_session),
) -> ReportActionResponse:
    report = await _require_report(session, report_id)
    if report.status not in (ReportStatus.RESOLVED, ReportStatus.CLOSED):
        raise HTTPException(status_code=409, detail="Report is not closed")

    payload = payload or ReportReopenRequest()
    if payload.action == "unblock_user" and payload.user_id is not None:
        user = await session.scalar(select(User).where(User.public_id == payload.user_id))
        if user is None:
            raise HTTPException(status_code=404, detail="User not found")
        user.is_active = True
        user.deleted_at = None
    elif payload.action == "restore_target":
        await _restore_target(session, report.target_type, report.target_id)

    report.status = ReportStatus.OPEN
    report.closed_at = None
    await session.commit()
    analytics_bus.publish("report.reopened")

    return ReportActionResponse(
        id=str(report.id),
        status=report.status,
        closed_at=report.closed_at,
        message="Report reopened",
    )
