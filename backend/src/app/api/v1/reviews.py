from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_session
from app.core.security import get_current_user
from app.models import Conversation, Listing, Review, User
from app.models.enums import ListingStatus
from app.schemas.limits import PathId
from app.schemas.review import ReviewCreate, ReviewCreated

router = APIRouter()


@router.post("/reviews", status_code=201)
async def create_review(
    payload: ReviewCreate,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> ReviewCreated:
    subject = await session.scalar(select(User).where(User.public_id == payload.subject_id))
    if subject is None:
        raise HTTPException(status_code=404, detail="Subject not found")
    if subject.id == current_user.id:
        raise HTTPException(status_code=400, detail="Cannot review yourself")

    conversation = await session.scalar(
        select(Conversation).where(Conversation.id == payload.conversation_id)
    )
    if conversation is None:
        raise HTTPException(status_code=404, detail="Conversation not found")
    if current_user.id not in (conversation.buyer_id, conversation.seller_id):
        raise HTTPException(status_code=403, detail="Not a participant in this conversation")

    other_id = (
        conversation.seller_id
        if current_user.id == conversation.buyer_id
        else conversation.buyer_id
    )
    if subject.id != other_id:
        raise HTTPException(
            status_code=400, detail="Subject must be the other participant in the conversation"
        )

    listing = await session.scalar(select(Listing).where(Listing.id == conversation.listing_id))
    # listings.buyer_id, not just status == SOLD: the listing is sold via
    # exactly one conversation (POST /conversations/{id}/mark-sold), but a
    # seller can have other conversations for the same listing with buyers
    # who never bought it. Checking status alone would let them review too.
    if listing is None or listing.status != ListingStatus.SOLD or listing.buyer_id != conversation.buyer_id:
        raise HTTPException(
            status_code=400, detail="Listing must be marked as sold via this conversation before leaving a review"
        )

    already_reviewed = await session.scalar(
        select(Review.id).where(
            Review.conversation_id == payload.conversation_id,
            Review.author_id == current_user.id,
        )
    )
    if already_reviewed:
        raise HTTPException(status_code=409, detail="You already reviewed this conversation")

    review = Review(
        conversation_id=payload.conversation_id,
        author_id=current_user.id,
        subject_id=subject.id,
        rating=payload.rating,
        body=payload.body,
    )
    session.add(review)

    # Keep the subject's rating/rating_count (a running sum + count, per the
    # column comment) in sync so GET /users/{public_id}'s average is correct.
    subject.rating += payload.rating
    subject.rating_count += 1

    await session.commit()

    return ReviewCreated(
        id=review.id,
        conversation_id=review.conversation_id,
        author_id=current_user.public_id,
        subject_id=subject.public_id,
        rating=review.rating,
        body=review.body,
        created_at=review.created_at,
    )


@router.delete("/reviews/{review_id}", status_code=204)
async def delete_review(
    review_id: PathId,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> Response:
    review = await session.get(Review, review_id)
    if review is None or review.deleted_at is not None:
        raise HTTPException(status_code=404, detail="Review not found")
    if review.author_id != current_user.id:
        raise HTTPException(status_code=403, detail="Only the author can delete this review")

    subject = await session.get(User, review.subject_id)
    if subject is not None:
        subject.rating -= review.rating
        subject.rating_count -= 1
    review.deleted_at = datetime.now(UTC)
    await session.commit()

    return Response(status_code=204)
