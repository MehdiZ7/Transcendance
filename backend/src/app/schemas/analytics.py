
import uuid
from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, Field
from pydantic.alias_generators import to_camel


class CamelModel(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)


# @router.get("/analytics/online-students")

class CampusOnlineCount(CamelModel):
    campus_id: str
    campus_name: str
    count: int


class OnlineStudentsData(CamelModel):
    total: int
    by_campus: list[CampusOnlineCount]
    peak_today: int
    updated_at: datetime


# @router.get("/analytics/listings-today")

class CategoryCount(CamelModel):
    category_id: str
    category_name: str
    count: int

class ListingsTodayData(CamelModel):
    count: int
    compared_to_yesterday_percent: float
    by_category: list[CategoryCount]
    date: date


# @router.get("/analytics/pending-reports")

class ReportsByTargetType(BaseModel):
    listing: int = 0
    message: int = 0
    user: int = 0
    review: int = 0


class PendingReportsData(CamelModel):
    count: int
    by_target_type: ReportsByTargetType
    urgent_count: int
    oldest_report_date: datetime | None


# @router.get("/analytics/sold-percentage")

class SoldListingsData(CamelModel):
    sold_count: int
    active_count: int
    total_count: int
    percentage: float
    average_time_to_sell_days: float


# @router.get("/analytics/category-distribution")

class CategoryDistributionItem(CamelModel):
    category_id: str
    category_name: str
    count: int
    percentage: float


class CategoryDistributionData(CamelModel):
    total_listings: int
    categories: list[CategoryDistributionItem]


# @router.get("/analytics/listings-between-dates")

class DailyListingCount(CamelModel):
    date: date
    count: int


class ListingsBetweenDatesData(CamelModel):
    start_date: date
    end_date: date
    total_count: int
    daily_breakdown: list[DailyListingCount]


# @router.get("/analytics/total-value")

class CategoryValueItem(CamelModel):
    category_id: str
    category_name: str
    total_value: int


class TotalListingsValueData(CamelModel):
    total_value: int
    active_value: int
    sold_value: int
    currency: str
    by_category: list[CategoryValueItem]


# @router.get("/analytics/average-price")

class CategoryPriceItem(CamelModel):
    category_id: str
    category_name: str
    average_price: float


class AverageListingPriceData(CamelModel):
    average_price: float
    median_price: float
    min_price: int
    max_price: int
    currency: str
    by_category: list[CategoryPriceItem]


# @router.get("/analytics/messages-count")

class MessagesCountData(CamelModel):
    total_messages: int
    messages_today: int
    total_conversations: int
    active_conversations_today: int
    average_messages_per_conversation: float


# @router.get("/analytics/top-liked")

class TopLikedListingItem(CamelModel):
    rank: int
    id: uuid.UUID
    public_id: uuid.UUID = Field(alias="public_id")
    title: str
    price: int
    currency: str
    category_name: str
    campus_name: str
    favorites_count: int = Field(alias="favorites_count")
    view_count: int = Field(alias="view_count")
    image_url: str | None = None
    seller_name: str


class TopLikedListingsData(CamelModel):
    listings: list[TopLikedListingItem]


# @router.get("/analytics")

class AnalyticsDashboardData(CamelModel):
    online_students: OnlineStudentsData
    listings_today: ListingsTodayData
    pending_reports: PendingReportsData
    sold_percentage: SoldListingsData
    category_distribution: CategoryDistributionData
    listings_between_dates: ListingsBetweenDatesData
    total_value: TotalListingsValueData
    average_price: AverageListingPriceData
    messages_count: MessagesCountData
    top_liked: TopLikedListingsData
