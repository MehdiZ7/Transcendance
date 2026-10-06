import type { CreateListingInput, Listing, ListingFilterParams, PaginatedResponse } from "@/types";
import { MAX_PRICE } from "@/lib/limits";
import { fetchApi } from "./client";

export const listingsApi = {
  // Get the paginated and filtered list of listings
  async getAll(params: ListingFilterParams = {}): Promise<PaginatedResponse<Listing>> {
    const page = Math.max(1, params.page || 1);
    const limit = params.limit || 30;

    const searchParams = new URLSearchParams();
    searchParams.set('page', String(page));
    searchParams.set('limit', String(limit));

    if (params.query) searchParams.set('q', params.query);
    // Only forward ids the API accepts (positive ints) and finite, in-range prices.
    const category = params.category || params.category_id;
    if (category && /^\d+$/.test(category) && Number(category) >= 1) {
      searchParams.set('categorie', category);
    }
    const location = params.location || params.location_id;
    if (location && /^\d+$/.test(location) && Number(location) >= 1) {
      searchParams.set('location', location);
    }
    if (typeof params.min_price === 'number' && Number.isFinite(params.min_price)) {
      searchParams.set('prix_min', String(Math.min(Math.max(0, Math.trunc(params.min_price)), MAX_PRICE)));
    }
    if (typeof params.max_price === 'number' && Number.isFinite(params.max_price)) {
      searchParams.set('prix_max', String(Math.min(Math.max(0, Math.trunc(params.max_price)), MAX_PRICE)));
    }
    if (params.sort || params.sort_by) {
      const rawSort = params.sort || params.sort_by || '';
      const sortValue =
        rawSort === 'date_desc' || rawSort === 'created_at_desc' ? 'recent' :
          rawSort === 'date_asc' ? 'oldest' :
            rawSort === 'prix_asc' ? 'price_asc' :
              rawSort === 'prix_desc' ? 'price_desc' :
                rawSort;
      if (sortValue) {
        searchParams.set('sort', sortValue);
      }
    }

    const queryString = searchParams.toString();
    return fetchApi<PaginatedResponse<Listing>>(`/listings?${queryString}`);
  },

  // get a user's listings (paged)
  async getByUser(
    userId: string,
    params: { page?: number; limit?: number } = {}
  ): Promise<PaginatedResponse<Listing>> {
    const searchParams = new URLSearchParams();
    searchParams.set('page', String(Math.max(1, params.page ?? 1)));
    searchParams.set('limit', String(params.limit ?? 12));
    return fetchApi<PaginatedResponse<Listing>>(
      `/users/${userId}/listings?${searchParams.toString()}`
    );
  },

  // get a user's favorites (paged)
  async getFavoritesByUser(
    userId: string,
    params: { page?: number; limit?: number } = {}
  ): Promise<PaginatedResponse<Listing>> {
    const searchParams = new URLSearchParams();
    searchParams.set('page', String(Math.max(1, params.page ?? 1)));
    searchParams.set('limit', String(params.limit ?? 12));
    return fetchApi<PaginatedResponse<Listing>>(
      `/users/${userId}/favorites?${searchParams.toString()}`
    );
  },

  // Get a listing by its public_id
  async getByPublicId(publicId: string): Promise<Listing | null> {
    try {
      return await fetchApi<Listing>(`/listings/${publicId}`);
    } catch {
      return null;
    }
  },

  // Create a listing
  async create(data: CreateListingInput): Promise<Listing> {
    return fetchApi<Listing>('/listings', {
      method: 'POST',
      body: JSON.stringify(data),
    });
  },

  // Add a listing to favorites
  async addFavorite(listingId: string): Promise<{ is_favorited: boolean; favorites_count: number }> {
    return fetchApi<{ is_favorited: boolean; favorites_count: number }>(`/listings/${listingId}/favorite`, {
      method: 'POST',
    });
  },

  // Remove a listing from favorites
  async removeFavorite(listingId: string): Promise<{ is_favorited: boolean; favorites_count: number }> {
    return fetchApi<{ is_favorited: boolean; favorites_count: number }>(`/listings/${listingId}/favorite`, {
      method: 'DELETE',
    });
  },

  // Delete a listing (moderation or owner)
  async delete(listingId: string): Promise<void> {
    await fetchApi<void>(`/listings/${listingId}`, { method: 'DELETE' });
  },

  // Mark a listing as sold (seller, without a conversation)
  async markSold(listingId: string): Promise<void> {
    await fetchApi<void>(`/listings/${listingId}/mark-sold`, { method: 'POST' });
  },
};
