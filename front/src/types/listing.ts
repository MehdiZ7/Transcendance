import type { PublicUser } from './user';

/**
 * Listing condition / wear level (`listings` table in schema.md)
 */
export type ListingCondition = 'new' | 'like_new' | 'good' | 'fair' | 'for_parts';

/**
 * Listing status (`listings` table in schema.md)
 */
export type ListingStatus = 'draft' | 'active' | 'sold' | 'expired' | 'archived' | 'deleted' | (string & {});

/**
 * Supported data types for dynamic category attributes
 */
export type CategoryAttributeDataType =
  | 'int'
  | 'dec'
  | 'bool'
  | 'enum'
  | 'text'
  | 'date'
  | (string & {});

/**
 * Listing category (`categories` table in schema.md)
 */
export interface Category {
  id: string;
  parent_id?: string | null;
  depth: number;
  category_name: string;
  is_leaf: boolean;
  parent?: Category | null;
  children?: Category[];
  attributes?: CategoryAttribute[];
}

/**
 * Category-specific attributes (`category_attributes` table in schema.md)
 */
export interface CategoryAttribute {
  id: string;
  category_id: string;
  key: string;
  data_type: CategoryAttributeDataType;
  unit?: string | null;
  is_required: boolean;
  is_filterable: boolean;
  options?: string[] | Record<string, unknown> | null;
}

/**
 * Geographical location for a listing (`locations` table in schema.md)
 */
export interface Location {
  id: string;
  location: string;
}

/**
 * Image associated with a listing (`listing_images` table in schema.md)
 */
export interface ListingImage {
  id: string;
  listing_id: string;
  storage_path: string;
  position: number;
  width?: number | null;
  height?: number | null;
  created_at: string;
}

/**
 * Listing entity (`listings` table in schema.md)
 */
export interface Listing {
  id: string;
  public_id: string;
  seller_id: string;
  category_id: string;
  title: string;
  body: string | null;
  price: number;
  currency?: string;
  condition?: ListingCondition | null;
  attributes?: Record<string, unknown> | null;
  location_id: string;
  status: ListingStatus;
  published_at?: string | null;
  expires_at?: string | null;
  cover_image_id?: string | null;
  view_count: number;
  search_vector?: string | null;
  created_at: string;
  updated_at: string;
  deleted_at?: string | null;
  buyer_id?: string | null;

  // Optional relations after joins
  seller?: PublicUser;
  buyer?: PublicUser;
  category?: Category;
  location?: Location;
  images?: ListingImage[];
  cover_image?: ListingImage | null;
  favorites_count?: number;
  is_favorited?: boolean;
}

/**
 * Filter parameters for listing search and retrieval
 */
export interface ListingFilterParams {
  page?: number;
  limit?: number;
  query?: string;
  category?: string;
  category_id?: string;
  location?: string;
  location_id?: string;
  min_price?: number;
  max_price?: number;
  sort?: string;
  sort_by?: 'price_asc' | 'price_desc' | 'created_at_desc' | 'view_count_desc';
  condition?: ListingCondition | ListingCondition[];
  status?: ListingStatus;
}

/**
 * DTO for creating a new listing
 */
export interface CreateListingInput {
  category_id: string;
  location_id: string;
  title: string;
  body: string;
  price: number;
  currency?: string;
  condition?: ListingCondition | null;
  attributes?: Record<string, unknown>;
  status?: ListingStatus;
  image_urls?: string[];
}
