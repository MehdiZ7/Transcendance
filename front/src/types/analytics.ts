// src/types/analytics.ts

export interface OnlineStudentsData {
  total: number;
  byCampus: Array<{
    campusId: string;
    campusName: string;
    count: number;
  }>;
  peakToday: number;
  updatedAt: string;
}

export interface ListingsTodayData {
  count: number;
  comparedToYesterdayPercent: number;
  byCategory: Array<{
    categoryId: string;
    categoryName: string;
    count: number;
  }>;
  date: string;
}

export interface PendingReportsData {
  count: number;
  byTargetType: {
    listing: number;
    message: number;
    user: number;
    review: number;
  };
  urgentCount: number;
  oldestReportDate: string | null;
}

export interface SoldListingsData {
  soldCount: number;
  activeCount: number;
  totalCount: number;
  percentage: number;
  averageTimeToSellDays: number;
}

export interface CategoryDistributionItem {
  categoryId: string;
  categoryName: string;
  count: number;
  percentage: number;
  color: string;
}

export interface CategoryDistributionData {
  totalListings: number;
  categories: CategoryDistributionItem[];
}

export interface DailyListingCount {
  date: string;
  count: number;
}

export interface ListingsBetweenDatesData {
  startDate: string;
  endDate: string;
  totalCount: number;
  dailyBreakdown: DailyListingCount[];
}

export interface CategoryValueItem {
  categoryId: string;
  categoryName: string;
  totalValue: number;
}

export interface TotalListingsValueData {
  totalValue: number;
  activeValue: number;
  soldValue: number;
  currency: string;
  byCategory: CategoryValueItem[];
}

export interface CategoryPriceItem {
  categoryId: string;
  categoryName: string;
  averagePrice: number;
}

export interface AverageListingPriceData {
  averagePrice: number;
  medianPrice: number;
  minPrice: number;
  maxPrice: number;
  currency: string;
  byCategory: CategoryPriceItem[];
}

export interface TopLikedListingItem {
  rank: number;
  id: string;
  public_id: string;
  title: string;
  price: number;
  currency: string;
  categoryName: string;
  campusName: string;
  favorites_count: number;
  view_count: number;
  imageUrl?: string;
  sellerName: string;
}

export interface TopLikedListingsData {
  listings: TopLikedListingItem[];
}
