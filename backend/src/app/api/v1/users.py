import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy import and_, delete, exists, func, or_, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased, joinedload

from app.core.config import settings
from app.core.db import get_session
from app.core.quotas import enforce
from app.core.security import get_current_user, get_current_user_optional
from app.core.serializers import to_listing_read, to_public_user
from app.core.uploads import delete_own_upload, is_allowed_image_ref
from app.models import (
    Conversation,
    Friend,
    Listing,
    ListingFavorite,
    ListingImage,
    Location,
    Review,
    User,
    UserBlock,
)
from app.models.enums import ListingStatus
from app.schemas.common import MessageResponse
from app.schemas.limits import PageNumber
from app.schemas.listing import ListingRead
from app.schemas.pagination import PaginatedResponse
from app.schemas.review import ReviewRead
from app.schemas.user import (
    MeProfile,
    MeUpdate,
    MeUpdated,
    OtherUserProfile,
    PublicUser,
    UserProfile,
)

_LISTING_RELATION_OPTIONS = (
    joinedload(Listing.seller),
    joinedload(Listing.category),
    joinedload(Listing.location),
)

router = APIRouter()


def _to_user_profile(user: User) -> UserProfile:
    return UserProfile(**to_public_user(user).model_dump(), role=user.role, created_at=user.created_at)


@router.get("/users/me", response_model=MeProfile | None)
async def get_me(
    current_user: User | None = Depends(get_current_user_optional),
    session: AsyncSession = Depends(get_session),
) -> MeProfile | Response:
    if current_user is None:
        return Response(status_code=204)

    friends_count = await session.scalar(
        select(func.count())
        .select_from(Friend)
        .where(
            Friend.status == "accepted",
            or_(Friend.requester_id == current_user.id, Friend.address_id == current_user.id),
        )
    )
    listings_count = await session.scalar(
        select(func.count())
        .select_from(Listing)
        .where(Listing.seller_id == current_user.id, Listing.deleted_at.is_(None))
    )
    reviews_count = await session.scalar(
        select(func.count())
        .select_from(Review)
        .where(Review.subject_id == current_user.id, Review.deleted_at.is_(None))
    )

    return MeProfile(
        **_to_user_profile(current_user).model_dump(),
        email=current_user.email,
        location_id=current_user.location_id,
        friends_count=friends_count or 0,
        listings_count=listings_count or 0,
        reviews_count=reviews_count or 0,
        has_password=current_user.password_hash is not None,
    )


@router.patch("/users/me")
async def update_me(
    payload: MeUpdate,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> MeUpdated:
    updates = payload.model_dump(exclude_unset=True)

    if "location_id" in updates and updates["location_id"] is not None:
        location_exists = await session.scalar(
            select(Location.id).where(Location.id == updates["location_id"])
        )
        if not location_exists:
            raise HTTPException(status_code=404, detail="Location not found")

    old_avatar = current_user.avatar_path
    avatar = updates.get("avatar_path")
    avatar_replaced = "avatar_path" in updates and avatar != old_avatar
    if (
        avatar
        and avatar_replaced  # the front sends the current one back untouched
        and not is_allowed_image_ref(avatar, current_user.public_id)
    ):
        raise HTTPException(status_code=422, detail="Invalid image reference")

    for field, value in updates.items():
        setattr(current_user, field, value)
    if updates:
        current_user.updated_at = datetime.now(UTC)
    await session.commit()

    if avatar_replaced and old_avatar:
        # Storage quotas are permanent otherwise: an avatar changed a dozen
        # times would fill it for nothing once uploads never got here
        delete_own_upload(old_avatar, current_user.public_id)

    return MeUpdated(
        public_id=current_user.public_id,
        display_name=current_user.display_name,
        bio=current_user.bio,
        avatar_path=current_user.avatar_path,
        location_id=current_user.location_id,
        updated_at=current_user.updated_at,
    )


@router.get("/users/{public_id}")
async def get_user(
    public_id: uuid.UUID,
    current_user: User | None = Depends(get_current_user_optional),
    session: AsyncSession = Depends(get_session),
) -> OtherUserProfile:
    """Public, but personalized when a session is present: has_blocked_me
    tells the front not to offer a friend request the API would refuse (403)."""
    user = await session.scalar(select(User).where(User.public_id == public_id))
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")

    has_blocked_me = False
    if current_user is not None and current_user.id != user.id:
        has_blocked_me = bool(
            await session.scalar(
                select(
                    exists().where(
                        UserBlock.user_blocking == user.id,
                        UserBlock.user_blocked == current_user.id,
                    )
                )
            )
        )
    return OtherUserProfile(**_to_user_profile(user).model_dump(), has_blocked_me=has_blocked_me)


@router.get("/users/{public_id}/reviews")
async def list_user_reviews(
    public_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
) -> list[ReviewRead]:
    subject_id = await session.scalar(select(User.id).where(User.public_id == public_id))
    if subject_id is None:
        raise HTTPException(status_code=404, detail="User not found")

    result = await session.execute(
        select(Review, User)
        .join(User, User.id == Review.author_id)
        .where(Review.subject_id == subject_id, Review.deleted_at.is_(None))
        .order_by(Review.created_at.desc())
    )

    return [
        ReviewRead(
            id=review.id,
            conversation_id=review.conversation_id,
            rating=review.rating,
            body=review.body,
            created_at=review.created_at,
            author=to_public_user(author),
        )
        for review, author in result.all()
    ]


@router.post("/users/{public_id}/block", status_code=200)
async def block_user(
    public_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> MessageResponse:
    """Blocking is more than the UserBlock row: it also deletes any
    friendship or pending request between the two, in either direction
    (nothing to delete if they were never friends - no Friend row is created
    for the block), and closes every conversation between them regardless
    of which one was buyer/seller on which listing.

    Deleting the friendship deletes their direct messages with it (the
    friend_messages rows go with the friends row, ON DELETE CASCADE), same as
    DELETE /friends/{public_id}."""
    target = await session.scalar(select(User).where(User.public_id == public_id))
    if target is None:
        raise HTTPException(status_code=404, detail="User not found")
    if target.id == current_user.id:
        raise HTTPException(status_code=400, detail="Cannot block yourself")

    already_blocked = await session.scalar(
        select(UserBlock.user_blocked).where(
            UserBlock.user_blocking == current_user.id, UserBlock.user_blocked == target.id
        )
    )
    if already_blocked is None:
        await enforce(
            session,
            current_user.id,
            select(func.count()).select_from(UserBlock).where(
                UserBlock.user_blocking == current_user.id
            ),
            settings.quota_blocks,
            "Too many blocked users: unblock some first",
        )

    # ON CONFLICT DO NOTHING rather than a SELECT-then-INSERT: two concurrent
    # block requests (double-click, two tabs) would otherwise both pass the
    # "not already blocked" check and the second INSERT would raise
    # IntegrityError on the composite PK.
    await session.execute(
        pg_insert(UserBlock)
        .values(user_blocking=current_user.id, user_blocked=target.id)
        .on_conflict_do_nothing()
    )

    await session.execute(
        delete(Friend).where(
            or_(
                and_(Friend.requester_id == current_user.id, Friend.address_id == target.id),
                and_(Friend.requester_id == target.id, Friend.address_id == current_user.id),
            )
        )
    )

    await session.execute(
        update(Conversation)
        .where(
            or_(
                and_(
                    Conversation.buyer_id == current_user.id,
                    Conversation.seller_id == target.id,
                ),
                and_(
                    Conversation.buyer_id == target.id,
                    Conversation.seller_id == current_user.id,
                ),
            ),
            Conversation.closed.is_(False),
        )
        .values(closed=True)
    )

    await session.commit()
    return MessageResponse(message="User blocked")


@router.delete("/users/{public_id}/block")
async def unblock_user(
    public_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> MessageResponse:
    """Lifts the block and reopens the conversations it closed - the friendship
    it deleted is not restored, that needs a fresh friend request."""
    target = await session.scalar(select(User).where(User.public_id == public_id))
    if target is None:
        raise HTTPException(status_code=404, detail="User not found")

    block = await session.scalar(
        select(UserBlock).where(
            UserBlock.user_blocking == current_user.id, UserBlock.user_blocked == target.id
        )
    )
    if block is not None:
        await session.delete(block)
        await session.execute(
            update(Conversation)
            .where(
                or_(
                    and_(
                        Conversation.buyer_id == current_user.id,
                        Conversation.seller_id == target.id,
                    ),
                    and_(
                        Conversation.buyer_id == target.id,
                        Conversation.seller_id == current_user.id,
                    ),
                ),
                Conversation.closed.is_(True),
            )
            .values(closed=False)
        )
        await session.commit()

    return MessageResponse(message="User unblocked")


@router.get("/users/me/blocks")
async def list_blocked_users(
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> list[PublicUser]:
    result = await session.execute(
        select(User)
        .join(UserBlock, UserBlock.user_blocked == User.id)
        .where(UserBlock.user_blocking == current_user.id)
        .order_by(UserBlock.created_at.desc())
    )
    return [to_public_user(user) for user in result.scalars().all()]


@router.get("/users/{public_id}/friends")
async def list_user_friends(
    public_id: uuid.UUID,
    _current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> list[PublicUser]:
    user_id = await session.scalar(select(User.id).where(User.public_id == public_id))
    if user_id is None:
        raise HTTPException(status_code=404, detail="User not found")

    result = await session.execute(
        select(User)
        .join(
            Friend,
            or_(
                and_(Friend.requester_id == user_id, Friend.address_id == User.id),
                and_(Friend.address_id == user_id, Friend.requester_id == User.id),
            ),
        )
        .where(Friend.status == "accepted")
    )
    return [to_public_user(friend) for friend in result.scalars().all()]


async def _paginate_listings(
    session: AsyncSession,
    conditions: list,
    order_by,
    page: int,
    limit: int,
    current_user: User | None,
) -> PaginatedResponse[ListingRead]:
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
        else False
    )

    result = await session.execute(
        select(Listing, ListingImage.storage_path, favorites_count_col, is_favorited_col)
        .outerjoin(ListingImage, ListingImage.id == Listing.cover_image_id)
        .options(*_LISTING_RELATION_OPTIONS)
        .where(*conditions)
        .order_by(order_by)
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


@router.get("/users/{public_id}/listings")
async def list_user_listings(
    public_id: uuid.UUID,
    page: PageNumber = 1,
    limit: int = Query(30, ge=1, le=100),
    current_user: User | None = Depends(get_current_user_optional),
    session: AsyncSession = Depends(get_session),
) -> PaginatedResponse[ListingRead]:
    """A user's active and sold listings, shown on their public profile -
    their own included, via their own public_id. No auth required, same as
    GET /users/{public_id} and GET /users/{public_id}/reviews."""
    seller_id = await session.scalar(select(User.id).where(User.public_id == public_id))
    if seller_id is None:
        raise HTTPException(status_code=404, detail="User not found")

    conditions = [
        Listing.seller_id == seller_id,
        Listing.status.in_((ListingStatus.ACTIVE, ListingStatus.SOLD)),
    ]
    return await _paginate_listings(
        session, conditions, Listing.created_at.desc(), page, limit, current_user
    )


@router.get("/users/{public_id}/favorites")
async def list_user_favorites(
    public_id: uuid.UUID,
    page: PageNumber = 1,
    limit: int = Query(30, ge=1, le=100),
    current_user: User | None = Depends(get_current_user_optional),
    session: AsyncSession = Depends(get_session),
) -> PaginatedResponse[ListingRead]:
    """A user's favorited listings, shown on their public profile - their
    own included, via their own public_id. No auth required, same as
    GET /users/{public_id}/listings; is_favorited reflects the viewer, not
    the profile owner."""
    target_user_id = await session.scalar(select(User.id).where(User.public_id == public_id))
    if target_user_id is None:
        raise HTTPException(status_code=404, detail="User not found")

    # Aliased: distinct from the unaliased ListingFavorite used below for
    # the viewer's own is_favorited, which is a different user entirely.
    target_favorite = aliased(ListingFavorite)
    conditions = (
        target_favorite.user_id == target_user_id,
        Listing.status != ListingStatus.DELETED,
    )

    count_query = (
        select(func.count())
        .select_from(target_favorite)
        .join(Listing, Listing.id == target_favorite.listing_id)
        .where(*conditions)
    )
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
        else False
    )

    favorited = await session.execute(
        select(Listing, ListingImage.storage_path, favorites_count_col, is_favorited_col)
        .join(target_favorite, target_favorite.listing_id == Listing.id)
        .outerjoin(ListingImage, ListingImage.id == Listing.cover_image_id)
        .options(*_LISTING_RELATION_OPTIONS)
        .where(*conditions)
        .order_by(target_favorite.created_at.desc())
        .offset((page - 1) * limit)
        .limit(limit)
    )

    data = [
        to_listing_read(listing, cover_path, favorites_count, is_favorited)
        for listing, cover_path, favorites_count, is_favorited in favorited.all()
    ]

    return PaginatedResponse(
        data=data,
        total=total,
        page=page,
        limit=limit,
        total_pages=-(-total // limit) if limit else 0,
    )
