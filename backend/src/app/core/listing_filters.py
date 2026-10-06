"""Listing filters shared by the admin analytics and the personal stats, so the
two cannot drift apart on what counts as a listing."""

from sqlalchemy import and_

from app.models import Listing
from app.models.enums import ListingStatus

# The listings that make up the stock: online (active) or sold, and not deleted.
# Drafts, expired, archived and deleted ones are not counted anywhere.
STOCK = and_(
    Listing.deleted_at.is_(None),
    Listing.status.in_([ListingStatus.ACTIVE, ListingStatus.SOLD]),
)
