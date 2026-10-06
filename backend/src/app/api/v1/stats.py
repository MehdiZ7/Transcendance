"""Personal stats: the caller's own selling and buying figures."""

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_session
from app.core.listing_filters import STOCK
from app.core.security import get_current_user
from app.models import Category, Listing, User
from app.models.enums import ListingStatus
from app.schemas.stats import (
    BuyingCategory,
    BuyingStats,
    ListingStats,
    MyStats,
    SellingCategory,
    SellingStats,
)

router = APIRouter()


def _average(total: int, count: int) -> float:
    return round(total / count, 2) if count else 0.0


def _by_category_order(name: str | None, weight: int) -> tuple[int, str]:
    """Biggest categories first, then by name (uncategorised after the named ones on a tie)."""
    return (-weight, name or "\uffff")


@router.get("/users/me/stats")
async def get_my_stats(
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> MyStats:
    """The caller's own figures, computed in SQL. Private: only /users/me.

    Selling: my listings in the STOCK (active or sold, not deleted), with
    their count, total value (sum of prices) and average price, and how they
    spread over categories. Buying: what I bought, meaning listings whose
    buyer_id is me (set when the seller marks it sold) that are sold and in the
    STOCK, so not deleted; total_spent is the sum of their prices. Prices are whole euros,
    the current price of the listing (there is no price history)."""
    mine = (Listing.seller_id == current_user.id, STOCK)

    per_status = {
        status: (count, int(total))
        for status, count, total in await session.execute(
            select(Listing.status, func.count(), func.coalesce(func.sum(Listing.price), 0))
            .where(*mine)
            .group_by(Listing.status)
        )
    }

    def listing_stats(status: ListingStatus) -> ListingStats:
        count, total = per_status.get(status, (0, 0))
        return ListingStats(count=count, total_value=total, average_price=_average(total, count))

    selling_categories: dict[int | None, SellingCategory] = {}
    for category_id, name, status, count in await session.execute(
        select(Listing.category_id, Category.category_name, Listing.status, func.count())
        .outerjoin(Category, Category.id == Listing.category_id)
        .where(*mine)
        .group_by(Listing.category_id, Category.category_name, Listing.status)
    ):
        entry = selling_categories.setdefault(
            category_id,
            SellingCategory(category_id=category_id, category_name=name, active=0, sold=0),
        )
        if status == ListingStatus.ACTIVE:
            entry.active += count
        else:
            entry.sold += count

    bought = [
        BuyingCategory(category_id=category_id, category_name=name, count=count, total_spent=int(total))
        for category_id, name, count, total in await session.execute(
            select(
                Listing.category_id,
                Category.category_name,
                func.count(),
                func.coalesce(func.sum(Listing.price), 0),
            )
            .outerjoin(Category, Category.id == Listing.category_id)
            .where(
                Listing.buyer_id == current_user.id,
                STOCK,
                Listing.status == ListingStatus.SOLD,
            )
            .group_by(Listing.category_id, Category.category_name)
        )
    ]
    bought.sort(key=lambda c: _by_category_order(c.category_name, c.count))
    bought_count = sum(c.count for c in bought)
    total_spent = sum(c.total_spent for c in bought)

    return MyStats(
        selling=SellingStats(
            active=listing_stats(ListingStatus.ACTIVE),
            sold=listing_stats(ListingStatus.SOLD),
            by_category=sorted(
                selling_categories.values(),
                key=lambda c: _by_category_order(c.category_name, c.active + c.sold),
            ),
        ),
        buying=BuyingStats(
            count=bought_count,
            total_spent=total_spent,
            average_price=_average(total_spent, bought_count),
            by_category=bought,
        ),
    )
