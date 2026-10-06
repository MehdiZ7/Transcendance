import asyncio
import json
from datetime import UTC, date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from fastapi import APIRouter, HTTPException, Depends, Query, Request
from sqlalchemy import Date, and_, cast, distinct, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload
from starlette.responses import StreamingResponse

from app.core import presence
from app.core.analytics_bus import analytics_bus
from app.core.db import get_session
from app.core.listing_filters import STOCK
from app.core.security import require_admin, require_admin_stream
from app.models import (
    Category,
    Conversation,
    Listing,
    ListingFavorite,
    ListingImage,
    Location,
    Message,
    Report,
    User,
)
from app.models.enums import ListingStatus, ReportStatus
from app.schemas.limits import AnalyticsDate
from app.schemas.analytics import (
    AnalyticsDashboardData,
    AverageListingPriceData,
    CampusOnlineCount,
    CategoryCount,
    CategoryDistributionData,
    CategoryDistributionItem,
    CategoryPriceItem,
    CategoryValueItem,
    DailyListingCount,
    ListingsBetweenDatesData,
    ListingsTodayData,
    MessagesCountData,
    OnlineStudentsData,
    PendingReportsData,
    ReportsByTargetType,
    SoldListingsData,
    TopLikedListingItem,
    TopLikedListingsData,
    TotalListingsValueData,
)

router = APIRouter()

TZ = ZoneInfo("Europe/Paris")
TOP_LIKED_LIMIT = 5
DEFAULT_RANGE_DAYS = 30
MAX_RANGE_DAYS = 366
URGENT_KEYWORDS = ("arnaque", "suspect", "harcèlement")
CURRENCY = "EUR"
PING_SECONDS = 20.0  # < nginx proxy_read_timeout (default 60 s)
RETRY_MS = 3000      # reconnection delay imposed on the browser


_POSTED = and_(
    Listing.deleted_at.is_(None),
    Listing.status.not_in([ListingStatus.DRAFT, ListingStatus.DELETED]),
)


def _local_day_bounds(day: date) -> tuple[datetime, datetime]:
    start = datetime.combine(day, time.min, tzinfo=TZ)
    return start, start + timedelta(days=1)


def _today() -> date:
    return datetime.now(TZ).date()


def _percent(part: float, whole: float) -> float:
    return round(part / whole * 100, 1) if whole else 0.0


async def _count_by_category(session: AsyncSession, *conditions) -> list[CategoryCount]:
    """Every category with the number of listings matching conditions."""
    rows = await session.execute(
        select(Category.id, Category.category_name, func.count(Listing.id))
        .outerjoin(Listing, and_(Listing.category_id == Category.id, *conditions))
        .group_by(Category.id, Category.category_name)
        .order_by(func.count(Listing.id).desc(), Category.category_name)
    )
    return [
        CategoryCount(category_id=str(cid), category_name=name, count=count)
        for cid, name, count in rows.all()
    ]


async def _online_students(session: AsyncSession) -> OnlineStudentsData:
    online_ids = presence.online_user_ids()
    total = len(online_ids)

    by_campus: list[CampusOnlineCount] = []
    if online_ids:
        rows = await session.execute(
            select(Location.id, Location.location, func.count(User.id))
            .join(User, User.location_id == Location.id)
            .where(User.id.in_(online_ids))
            .group_by(Location.id, Location.location)
            .order_by(func.count(User.id).desc(), Location.location)
        )
        by_campus = [
            CampusOnlineCount(campus_id=str(lid), campus_name=name, count=count)
            for lid, name, count in rows.all()
        ]

    return OnlineStudentsData(
        total=total,
        by_campus=by_campus,
        peak_today=presence.record_peak(total, _today()),
        updated_at=datetime.now(UTC),
    )


@router.get("/analytics/online-students")
async def online_students(
    _current_user: User = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
) -> OnlineStudentsData:
    return await _online_students(session)


def _growth(current: int, previous: int) -> float:
    if previous == 0:
        return 100.0 if current else 0.0
    return round((current - previous) / previous * 100, 1)


async def _listings_today(session: AsyncSession) -> ListingsTodayData:
    today = _today()
    start, end = _local_day_bounds(today)
    y_start, y_end = _local_day_bounds(today - timedelta(days=1))

    async def _count(lo: datetime, hi: datetime) -> int:
        return (
            await session.scalar(
                select(func.count())
                .select_from(Listing)
                .where(_POSTED, Listing.created_at >= lo, Listing.created_at < hi)
            )
            or 0
        )

    count = await _count(start, end)
    yesterday = await _count(y_start, y_end)

    return ListingsTodayData(
        count=count,
        compared_to_yesterday_percent=_growth(count, yesterday),
        by_category=await _count_by_category(
            session, _POSTED, Listing.created_at >= start, Listing.created_at < end
        ),
        date=today,
    )


@router.get("/analytics/listings-today")
async def listings_today(
    _current_user: User = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
) -> ListingsTodayData:
    return await _listings_today(session)


async def _pending_reports(session: AsyncSession) -> PendingReportsData:
    pending = Report.status == ReportStatus.OPEN

    rows = await session.execute(
        select(Report.target_type, func.count())
        .where(pending)
        .group_by(Report.target_type)
    )
    by_type = dict(rows.all())

    urgent = (
        await session.scalar(
            select(func.count())
            .select_from(Report)
            .where(
                pending,
                or_(*(Report.reason.ilike(f"%{kw}%") for kw in URGENT_KEYWORDS)),
            )
        )
        or 0
    )

    return PendingReportsData(
        count=sum(by_type.values()),
        by_target_type=ReportsByTargetType(**by_type),
        urgent_count=urgent,
        oldest_report_date=await session.scalar(
            select(func.min(Report.created_at)).where(pending)
        ),
    )


@router.get("/analytics/pending-reports")
async def pending_reports(
    _current_user: User = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
) -> PendingReportsData:
    return await _pending_reports(session)


async def _sold_percentage(session: AsyncSession) -> SoldListingsData:
    rows = await session.execute(
        select(Listing.status, func.count()).where(STOCK).group_by(Listing.status)
    )
    counts = dict(rows.all())
    sold = counts.get(ListingStatus.SOLD, 0)
    active = counts.get(ListingStatus.ACTIVE, 0)

    # No sold_at column exists, so use updated_at as the sale time
    # (set by POST /conversations/{id}/mark-sold).
    # Any later edit of a sold listing would shift it.
    seconds = await session.scalar(
        select(
            func.avg(
                func.extract(
                    "epoch",
                    func.coalesce(Listing.updated_at, Listing.created_at)
                    - Listing.created_at,
                )
            )
        ).where(Listing.deleted_at.is_(None), Listing.status == ListingStatus.SOLD)
    )

    return SoldListingsData(
        sold_count=sold,
        active_count=active,
        total_count=sold + active,
        percentage=_percent(sold, sold + active),
        average_time_to_sell_days=round(float(seconds or 0) / 86400, 1),
    )


@router.get("/analytics/sold-percentage")
async def sold_percentage(
    _current_user: User = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
) -> SoldListingsData:
    return await _sold_percentage(session)


async def _category_distribution(session: AsyncSession) -> CategoryDistributionData:
    by_category = await _count_by_category(session, _POSTED)
    total = sum(item.count for item in by_category)
    return CategoryDistributionData(
        total_listings=total,
        categories=[
            CategoryDistributionItem(
                category_id=item.category_id,
                category_name=item.category_name,
                count=item.count,
                percentage=_percent(item.count, total),
            )
            for item in by_category
        ],
    )


@router.get("/analytics/category-distribution")
async def category_distribution(
    _current_user: User = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
) -> CategoryDistributionData:
    return await _category_distribution(session)


def _resolve_range(start: date | None, end: date | None) -> tuple[date, date]:
    end = end or _today()
    start = start or end - timedelta(days=DEFAULT_RANGE_DAYS)
    if start > end:
        start, end = end, start
    if (end - start).days > MAX_RANGE_DAYS:
        raise HTTPException(
            status_code=422, detail=f"Range cannot exceed {MAX_RANGE_DAYS} days"
        )
    return start, end


async def _listings_between_dates(
    session: AsyncSession, start: date | None, end: date | None
) -> ListingsBetweenDatesData:
    start, end = _resolve_range(start, end)
    lo, _ = _local_day_bounds(start)
    _, hi = _local_day_bounds(end)
    day_col = cast(func.timezone(TZ.key, Listing.created_at), Date)
    rows = await session.execute(
        select(day_col, func.count())
        .where(_POSTED, Listing.created_at >= lo, Listing.created_at < hi)
        .group_by(day_col)
    )
    counts = dict(rows.all())

    breakdown = [
        DailyListingCount(date=day, count=counts.get(day, 0))
        for day in (start + timedelta(days=i) for i in range((end - start).days + 1))
    ]
    return ListingsBetweenDatesData(
        start_date=start,
        end_date=end,
        total_count=sum(d.count for d in breakdown),
        daily_breakdown=breakdown,
    )


@router.get("/analytics/listings-between-dates")
async def listings_between_dates(
    start_date: AnalyticsDate | None = Query(None, alias="startDate", description="YYYY-MM-DD"),
    end_date: AnalyticsDate | None = Query(None, alias="endDate", description="YYYY-MM-DD"),
    _current_user: User = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
) -> ListingsBetweenDatesData:
    return await _listings_between_dates(session, start_date, end_date)


async def _total_value(session: AsyncSession) -> TotalListingsValueData:
    rows = await session.execute(
        select(Listing.status, func.coalesce(func.sum(Listing.price), 0))
        .where(STOCK)
        .group_by(Listing.status)
    )
    sums = dict(rows.all())
    active = int(sums.get(ListingStatus.ACTIVE, 0))
    sold = int(sums.get(ListingStatus.SOLD, 0))

    cat_rows = await session.execute(
        select(
            Category.id,
            Category.category_name,
            func.coalesce(func.sum(Listing.price), 0),
        )
        .outerjoin(Listing, and_(Listing.category_id == Category.id, STOCK))
        .group_by(Category.id, Category.category_name)
        .order_by(
            func.coalesce(func.sum(Listing.price), 0).desc(), Category.category_name
        )
    )

    return TotalListingsValueData(
        total_value=active + sold,
        active_value=active,
        sold_value=sold,
        currency=CURRENCY,
        by_category=[
            CategoryValueItem(
                category_id=str(cid), category_name=name, total_value=int(total)
            )
            for cid, name, total in cat_rows.all()
        ],
    )


@router.get("/analytics/total-value")
async def total_value(
    _current_user: User = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
) -> TotalListingsValueData:
    return await _total_value(session)


async def _average_price(session: AsyncSession) -> AverageListingPriceData:
    priced = and_(_POSTED, Listing.price > 0)

    avg, median, low, high = (
        await session.execute(
            select(
                func.avg(Listing.price),
                func.percentile_cont(0.5).within_group(Listing.price.asc()),
                func.min(Listing.price),
                func.max(Listing.price),
            ).where(priced)
        )
    ).one()

    cat_rows = await session.execute(
        select(
            Category.id,
            Category.category_name,
            func.coalesce(func.avg(Listing.price), 0),
        )
        .outerjoin(Listing, and_(Listing.category_id == Category.id, priced))
        .group_by(Category.id, Category.category_name)
        .order_by(Category.category_name)
    )

    return AverageListingPriceData(
        average_price=round(float(avg or 0), 2),
        median_price=round(float(median or 0), 2),
        min_price=int(low or 0),
        max_price=int(high or 0),
        currency=CURRENCY,
        by_category=[
            CategoryPriceItem(
                category_id=str(cid),
                category_name=name,
                average_price=round(float(a), 2),
            )
            for cid, name, a in cat_rows.all()
        ],
    )


@router.get("/analytics/average-price")
async def average_price(
    _current_user: User = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
) -> AverageListingPriceData:
    return await _average_price(session)


async def _messages_count(session: AsyncSession) -> MessagesCountData:
    start, end = _local_day_bounds(_today())
    today = and_(Message.created_at >= start, Message.created_at < end)

    total, today_count, active_today = (
        await session.execute(
            select(
                func.count(),
                func.count().filter(today),
                func.count(distinct(Message.conversation_id)).filter(today),
            ).where(Message.deleted_at.is_(None))
        )
    ).one()

    conversations = (
        await session.scalar(select(func.count()).select_from(Conversation)) or 0
    )

    return MessagesCountData(
        total_messages=total,
        messages_today=today_count,
        total_conversations=conversations,
        active_conversations_today=active_today,
        average_messages_per_conversation=round(total / conversations, 1)
        if conversations
        else 0.0,
    )


@router.get("/analytics/messages-count")
async def messages_count(
    _current_user: User = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
) -> MessagesCountData:
    return await _messages_count(session)


async def _top_liked(session: AsyncSession) -> TopLikedListingsData:
    favorites_count = (
        select(func.count())
        .select_from(ListingFavorite)
        .where(ListingFavorite.listing_id == Listing.id)
        .correlate(Listing)
        .scalar_subquery()
    )
    rows = await session.execute(
        select(Listing, ListingImage.storage_path, favorites_count)
        .outerjoin(ListingImage, ListingImage.id == Listing.cover_image_id)
        .options(
            joinedload(Listing.seller),
            joinedload(Listing.category),
            joinedload(Listing.location),
        )
        .where(Listing.deleted_at.is_(None), Listing.status == ListingStatus.ACTIVE)
        .order_by(
            favorites_count.desc(), Listing.view_count.desc(), Listing.created_at.desc()
        )
        .limit(TOP_LIKED_LIMIT)
    )
    return TopLikedListingsData(
        listings=[
            TopLikedListingItem(
                rank=rank,
                id=listing.public_id,
                public_id=listing.public_id,
                title=listing.title,
                price=listing.price,
                currency=listing.currency,
                category_name=listing.category.category_name
                if listing.category
                else "Autre",
                campus_name=listing.location.location if listing.location else "—",
                favorites_count=favorites,
                view_count=listing.view_count,
                image_url=cover_path,
                seller_name=listing.seller.display_name,
            )
            for rank, (listing, cover_path, favorites) in enumerate(rows.all(), start=1)
        ]
    )


@router.get("/analytics/top-liked")
async def top_liked(
    _current_user: User = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
) -> TopLikedListingsData:
    return await _top_liked(session)


@router.get("/analytics")
async def dashboard(
    start_date: AnalyticsDate | None = Query(None, alias="startDate", description="YYYY-MM-DD"),
    end_date: AnalyticsDate | None = Query(None, alias="endDate", description="YYYY-MM-DD"),
    _current_user: User = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
) -> AnalyticsDashboardData:
    return AnalyticsDashboardData(
        online_students=await _online_students(session),
        listings_today=await _listings_today(session),
        pending_reports=await _pending_reports(session),
        sold_percentage=await _sold_percentage(session),
        category_distribution=await _category_distribution(session),
        listings_between_dates=await _listings_between_dates(
            session, start_date, end_date
        ),
        total_value=await _total_value(session),
        average_price=await _average_price(session),
        messages_count=await _messages_count(session),
        top_liked=await _top_liked(session),
    )


@router.get("/analytics/stream", include_in_schema=False)
async def stream_analytics_events(
    request: Request,
    _current_user: User = Depends(require_admin_stream),
) -> StreamingResponse:
    """Server-Sent Events stream of dashboard invalidations.

    No business data goes through it: the frontend refetches the REST endpoints.
    """

    async def event_generator():
        # Subscribe INSIDE the generator: if the response is never iterated
        # (client already gone), the `finally` would not run and the queue
        # would stay subscribed forever.
        queue = analytics_bus.subscribe()
        try:
            yield f"retry: {RETRY_MS}\n\n"
            yield "event: connected\ndata: {}\n\n"
            while not await request.is_disconnected():
                try:
                    async with asyncio.timeout(PING_SECONDS):
                        payload = await queue.get()
                except TimeoutError:
                    yield ": ping\n\n"  # SSE comment: keeps the connection alive
                    continue
                yield f"event: analytics_update\ndata: {json.dumps(payload)}\n\n"
        finally:
            analytics_bus.unsubscribe(queue)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",  # disables nginx buffering
        },
    )
