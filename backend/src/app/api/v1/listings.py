import uuid
from datetime import UTC, datetime
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy import and_, delete, func, literal, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload, selectinload

from app.core.analytics_bus import analytics_bus
from app.core.config import settings
from app.core.db import get_session
from app.core.quotas import enforce, since_window
from app.core.ratelimit import limit_listings
from app.core.security import get_current_user, get_current_user_optional
from app.core.serializers import to_listing_read, to_public_user
from app.core.uploads import delete_own_upload, is_allowed_image_ref
from app.models import Category, Listing, ListingFavorite, ListingImage, Location, User
from app.models.enums import ListingStatus
from app.schemas.catalog import CategoryRead, LocationRead
from app.schemas.limits import (
    MAX_DB_ID,
    MAX_PRICE,
    MAX_SEARCH_LENGTH,
    NoNul,
    PageNumber,
)
from app.schemas.listing import (
    FavoriteResponse,
    ListingCreate,
    ListingDetail,
    ListingImageRead,
    ListingRead,
)
from app.schemas.pagination import PaginatedResponse

router = APIRouter()

SortOption = Literal["recent", "oldest", "price_asc", "price_desc", "likes_desc"]

_RELATION_OPTIONS = (
    joinedload(Listing.seller),
    joinedload(Listing.category),
    joinedload(Listing.location),
)
_DETAIL_OPTIONS = (*_RELATION_OPTIONS, selectinload(Listing.images))


def _order_by(sort: SortOption):
    if sort == "oldest":
        return Listing.created_at.asc()
    if sort == "price_asc":
        return Listing.price.asc()
    if sort == "price_desc":
        return Listing.price.desc()
    if sort == "likes_desc":
        favorites_count = (
            select(func.count())
            .select_from(ListingFavorite)
            .where(ListingFavorite.listing_id == Listing.id)
            .correlate(Listing)
            .scalar_subquery()
        )
        return favorites_count.desc()
    return Listing.created_at.desc()


async def _to_detail(
    session: AsyncSession, listing: Listing, current_user: User | None
) -> ListingDetail:
    favorites_count = await session.scalar(
        select(func.count())
        .select_from(ListingFavorite)
        .where(ListingFavorite.listing_id == listing.id)
    )
    is_favorited = (
        await session.scalar(
            select(ListingFavorite.listing_id).where(
                ListingFavorite.listing_id == listing.id,
                ListingFavorite.user_id == current_user.id,
            )
        )
        if current_user is not None
        else None
    )

    cover_image_path = next(
        (image.storage_path for image in listing.images if image.id == listing.cover_image_id),
        None,
    )
    return ListingDetail(
        public_id=listing.public_id,
        title=listing.title,
        body=listing.body,
        price=listing.price,
        currency=listing.currency,
        condition=listing.condition,
        attributes=listing.attributes,
        status=listing.status,
        view_count=listing.view_count,
        favorites_count=favorites_count or 0,
        is_favorited=is_favorited is not None,
        published_at=listing.published_at,
        expires_at=listing.expires_at,
        created_at=listing.created_at,
        updated_at=listing.updated_at,
        cover_image_id=cover_image_path,
        seller=to_public_user(listing.seller),
        category=CategoryRead.model_validate(listing.category) if listing.category else None,
        location=LocationRead.model_validate(listing.location) if listing.location else None,
        images=[ListingImageRead.model_validate(image) for image in listing.images],
    )


@router.get("/listings")
async def list_listings(
    page: PageNumber = 1,
    limit: int = Query(30, ge=1, le=100),
    q: Annotated[str | None, Query(max_length=MAX_SEARCH_LENGTH), NoNul] = None,
    categorie: int | None = Query(None, ge=1, le=MAX_DB_ID),
    location: int | None = Query(None, ge=1, le=MAX_DB_ID),
    prix_min: int | None = Query(None, ge=0, le=MAX_PRICE),
    prix_max: int | None = Query(None, ge=0, le=MAX_PRICE),
    sort: SortOption = "recent",
    current_user: User | None = Depends(get_current_user_optional),
    session: AsyncSession = Depends(get_session),
) -> PaginatedResponse[ListingRead]:
    conditions = [
        Listing.status == ListingStatus.ACTIVE,
        # A suspended or removed seller can no longer answer a buyer: same
        # test as the one that refuses their session (load_active_user)
        Listing.seller.has(and_(User.is_active.is_(True), User.deleted_at.is_(None))),
    ]
    if current_user is not None:
        conditions.append(Listing.seller_id != current_user.id)
    if q:
        pattern = f"%{q}%"
        conditions.append(
            or_(Listing.title.ilike(pattern), Listing.body.ilike(pattern))
        )
    if categorie is not None:
        conditions.append(Listing.category_id == categorie)
    if location is not None:
        conditions.append(Listing.location_id == location)
    if prix_min is not None:
        conditions.append(Listing.price >= prix_min)
    if prix_max is not None:
        conditions.append(Listing.price <= prix_max)

    count_query = select(func.count()).select_from(select(Listing.id).where(*conditions).subquery())
    total = await session.scalar(count_query) or 0

    favorites_count_col = (
        select(func.count())
        .select_from(ListingFavorite)
        .where(ListingFavorite.listing_id == Listing.id)
        .correlate(Listing)
        .scalar_subquery()
    )
    is_favorited_col = (
        select(ListingFavorite.listing_id)
        .where(
            ListingFavorite.listing_id == Listing.id,
            ListingFavorite.user_id == current_user.id,
        )
        .correlate(Listing)
        .exists()
        if current_user is not None
        else literal(False)
    )

    result = await session.execute(
        select(Listing, ListingImage.storage_path, favorites_count_col, is_favorited_col)
        .outerjoin(ListingImage, ListingImage.id == Listing.cover_image_id)
        .options(*_RELATION_OPTIONS)
        .where(*conditions)
        .order_by(_order_by(sort))
        .offset((page - 1) * limit)
        .limit(limit)
    )

    data = [
        to_listing_read(listing, cover_path, favorites_count, is_favorited)
        for listing, cover_path, favorites_count, is_favorited in result.all()
    ]

    return PaginatedResponse(
        data=data,
        total=total,
        page=page,
        limit=limit,
        total_pages=-(-total // limit) if limit else 0,
    )


@router.get("/listings/{public_id}")
async def get_listing(
    public_id: uuid.UUID,
    current_user: User | None = Depends(get_current_user_optional),
    session: AsyncSession = Depends(get_session),
) -> ListingDetail:
    result = await session.execute(
        select(Listing)
        .where(Listing.public_id == public_id, Listing.status != ListingStatus.DELETED)
        .options(*_DETAIL_OPTIONS)
    )
    listing = result.unique().scalar_one_or_none()
    if listing is None:
        raise HTTPException(status_code=404, detail="Listing not found")

    return await _to_detail(session, listing, current_user)


@router.post("/listings", status_code=201, dependencies=[Depends(limit_listings)])
async def create_listing(
    payload: ListingCreate,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> ListingDetail:
    if not await session.scalar(select(Category.id).where(Category.id == payload.category_id)):
        raise HTTPException(status_code=404, detail="Category not found")
    if not await session.scalar(select(Location.id).where(Location.id == payload.location_id)):
        raise HTTPException(status_code=404, detail="Location not found")

    await enforce(
        session,
        current_user.id,
        select(func.count()).select_from(Listing).where(
            Listing.seller_id == current_user.id,
            Listing.deleted_at.is_(None),
            Listing.status.in_((ListingStatus.ACTIVE, ListingStatus.DRAFT)),
        ),
        settings.quota_active_listings,
        "Too many active listings: sell or delete some first",
    )
    await enforce(
        session,
        current_user.id,
        select(func.count()).select_from(Listing).where(
            Listing.seller_id == current_user.id, Listing.created_at > since_window()
        ),
        settings.quota_listings_per_day,
        "Too many listings created today, try again later",
        status_code=429,
    )

    if not all(is_allowed_image_ref(url, current_user.public_id) for url in payload.image_urls):
        raise HTTPException(status_code=422, detail="Invalid image reference")

    listing = Listing(
        seller_id=current_user.id,
        category_id=payload.category_id,
        location_id=payload.location_id,
        title=payload.title,
        body=payload.body,
        price=payload.price,
        currency=payload.currency,
        condition=payload.condition,
        attributes=payload.attributes,
        status=ListingStatus.ACTIVE,
    )
    session.add(listing)
    await session.flush()

    cover_image: ListingImage | None = None
    for position, url in enumerate(payload.image_urls):
        image = ListingImage(listing_id=listing.id, storage_path=url, position=position)
        session.add(image)
        if cover_image is None:
            cover_image = image

    if cover_image is not None:
        await session.flush()
        listing.cover_image_id = cover_image.id

    await session.commit()
    analytics_bus.publish("listing.created")


    result = await session.execute(
        select(Listing).where(Listing.id == listing.id).options(*_DETAIL_OPTIONS)
    )
    listing = result.unique().scalar_one()

    return await _to_detail(session, listing, current_user)


@router.delete("/listings/{public_id}", status_code=204)
async def delete_listing(
    public_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> Response:
    listing = await session.scalar(
        select(Listing).where(
            Listing.public_id == public_id,
            Listing.status != ListingStatus.DELETED
        )
    )
    if listing is None:
        raise HTTPException(status_code=404, detail="Listing not found")
    if listing.seller_id != current_user.id:
        raise HTTPException(status_code=403, detail="Only the seller can delete this listing")
    if listing.status == ListingStatus.SOLD:
        # POST /reviews requires status == SOLD
        # deleting a sold listing let the seller stop possibility of reviewing
        raise HTTPException(status_code=409, detail="Cannot delete a sold listing")

    # Soft delete
    # conversations.listing_id is ON DELETE CASCADE
    # a real DELETE would wipe conversations and their messages
    listing.status = ListingStatus.DELETED
    listing.deleted_at = datetime.now(UTC)
    await session.commit()
    analytics_bus.publish("listing.deleted")

    # Storage quotas are permanent otherwise: a deleted listing's photos
    # would fill it for nothing once the listing itself is gone for good
    paths = await session.scalars(
        select(ListingImage.storage_path).where(ListingImage.listing_id == listing.id)
    )
    for path in paths:
        delete_own_upload(path, current_user.public_id)

    return Response(status_code=204)


@router.post("/listings/{public_id}/mark-sold", status_code=204)
async def mark_listing_sold(
    public_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> Response:
    """Mark a listing as sold directly, without going through a conversation.

    The buyer stays unknown (buyer_id NULL): no review can be left for such a
    sale, which is fine since the review flow requires an identified buyer.
    """
    listing = await session.scalar(
        select(Listing).where(
            Listing.public_id == public_id,
            Listing.status != ListingStatus.DELETED,
        )
    )
    if listing is None:
        raise HTTPException(status_code=404, detail="Listing not found")
    if listing.seller_id != current_user.id:
        raise HTTPException(status_code=403, detail="Only the seller can mark this listing as sold")
    if listing.status != ListingStatus.ACTIVE:
        raise HTTPException(status_code=409, detail="Listing is not active")

    listing.status = ListingStatus.SOLD
    listing.updated_at = datetime.now(UTC)
    await session.commit()
    return Response(status_code=204)


async def _get_listing_or_404(session: AsyncSession, public_id: uuid.UUID) -> Listing:
    listing = await session.scalar(select(Listing).where(Listing.public_id == public_id))
    if listing is None:
        raise HTTPException(status_code=404, detail="Listing not found")
    return listing


async def _favorites_count(session: AsyncSession, listing_id: int) -> int:
    return (
        await session.scalar(
            select(func.count())
            .select_from(ListingFavorite)
            .where(ListingFavorite.listing_id == listing_id)
        )
        or 0
    )


@router.post("/listings/{public_id}/favorite")
async def add_favorite(
    public_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> FavoriteResponse:
    listing = await _get_listing_or_404(session, public_id)

    existing = await session.scalar(
        select(ListingFavorite).where(
            ListingFavorite.listing_id == listing.id,
            ListingFavorite.user_id == current_user.id,
        )
    )
    if existing is None:
        await enforce(
            session,
            current_user.id,
            select(func.count()).select_from(ListingFavorite).where(
                ListingFavorite.user_id == current_user.id
            ),
            settings.quota_favorites,
            "Too many favorites: remove some first",
        )
        session.add(ListingFavorite(listing_id=listing.id, user_id=current_user.id))
        await session.commit()
        analytics_bus.publish("favorite.added")

    return FavoriteResponse(
        is_favorited=True,
        favorites_count=await _favorites_count(session, listing.id),
    )


@router.delete("/listings/{public_id}/favorite")
async def remove_favorite(
    public_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> FavoriteResponse:
    listing = await _get_listing_or_404(session, public_id)

    await session.execute(
        delete(ListingFavorite).where(
            ListingFavorite.listing_id == listing.id,
            ListingFavorite.user_id == current_user.id,
        )
    )
    await session.commit()
    analytics_bus.publish("favorite.removed")

    return FavoriteResponse(
        is_favorited=False,
        favorites_count=await _favorites_count(session, listing.id),
    )
