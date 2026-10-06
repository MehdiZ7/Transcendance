from app.models import Listing, User
from app.schemas.auth import CurrentUser
from app.schemas.catalog import CategoryRead, LocationRead
from app.schemas.listing import ListingRead
from app.schemas.user import PublicUser


def to_public_user(user: User) -> PublicUser:
    return PublicUser(
        public_id=user.public_id,
        display_name=user.display_name,
        avatar_path=user.avatar_path,
        bio=user.bio,
        rating=(user.rating / user.rating_count) if user.rating_count else 0.0,
        rating_count=user.rating_count,
        is_active=user.is_active,
    )


def to_current_user(user: User) -> CurrentUser:
    return CurrentUser(
        public_id=user.public_id,
        display_name=user.display_name,
        email=user.email,
        role=user.role,
        avatar_path=user.avatar_path,
        bio=user.bio,
        has_password=user.password_hash is not None,
    )


def to_listing_read(
    listing: Listing, cover_image_path: str | None, favorites_count: int, is_favorited: bool
) -> ListingRead:
    return ListingRead(
        public_id=listing.public_id,
        title=listing.title,
        body=listing.body,
        price=listing.price,
        currency=listing.currency,
        condition=listing.condition,
        status=listing.status,
        view_count=listing.view_count,
        created_at=listing.created_at,
        updated_at=listing.updated_at,
        cover_image_id=cover_image_path,
        favorites_count=favorites_count,
        is_favorited=is_favorited,
        seller=to_public_user(listing.seller),
        category=CategoryRead.model_validate(listing.category) if listing.category else None,
        location=LocationRead.model_validate(listing.location) if listing.location else None,
    )
