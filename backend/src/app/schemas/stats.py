"""GET /users/me/stats: the caller's own selling and buying figures.

Prices are whole euros, the unit of `Listing.price`. Averages are rounded to
two decimals and are 0 when there is nothing to average."""

from pydantic import BaseModel


class ListingStats(BaseModel):
    count: int
    total_value: int
    average_price: float


class SellingCategory(BaseModel):
    category_id: int | None
    category_name: str | None
    active: int
    sold: int


class SellingStats(BaseModel):
    active: ListingStats
    sold: ListingStats
    by_category: list[SellingCategory]


class BuyingCategory(BaseModel):
    category_id: int | None
    category_name: str | None
    count: int
    total_spent: int


class BuyingStats(BaseModel):
    count: int
    total_spent: int
    average_price: float
    by_category: list[BuyingCategory]


class MyStats(BaseModel):
    selling: SellingStats
    buying: BuyingStats
