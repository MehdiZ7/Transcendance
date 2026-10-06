/**
 * Types matching GET /api/v1/users/me/stats
 */

export interface ListingStats {
  count: number;
  total_value: number;
  average_price: number;
}

export interface SellingCategory {
  category_id: number | null;
  category_name: string | null;
  active: number;
  sold: number;
}

export interface SellingStats {
  active: ListingStats;
  sold: ListingStats;
  by_category: SellingCategory[];
}

export interface BuyingCategory {
  category_id: number | null;
  category_name: string | null;
  count: number;
  total_spent: number;
}

export interface BuyingStats {
  count: number;
  total_spent: number;
  average_price: number;
  by_category: BuyingCategory[];
}

export interface MyStats {
  selling: SellingStats;
  buying: BuyingStats;
}
