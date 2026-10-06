import type {
  OnlineStudentsData,
  ListingsTodayData,
  PendingReportsData,
  SoldListingsData,
  CategoryDistributionData,
  ListingsBetweenDatesData,
  TotalListingsValueData,
  AverageListingPriceData,
  TopLikedListingsData,
} from '@/types';
import { fetchApi, ApiError } from './client';

export const analyticsApi = {
  async getOnlineStudents(): Promise<OnlineStudentsData> {
    return fetchApi<OnlineStudentsData>('/analytics/online-students');
  },

  async getListingsToday(): Promise<ListingsTodayData> {
    return fetchApi<ListingsTodayData>('/analytics/listings-today');
  },

  async getPendingReports(): Promise<PendingReportsData> {
    return fetchApi<PendingReportsData>('/analytics/pending-reports');
  },

  async getSoldPercentage(): Promise<SoldListingsData> {
    return fetchApi<SoldListingsData>('/analytics/sold-percentage');
  },

  async getCategoryDistribution(): Promise<CategoryDistributionData> {
    return fetchApi<CategoryDistributionData>('/analytics/category-distribution');
  },

  async getListingsBetweenDates(
    startDate?: string,
    endDate?: string
  ): Promise<ListingsBetweenDatesData> {
    const params = new URLSearchParams();
    if (startDate) params.set('startDate', startDate);
    if (endDate) params.set('endDate', endDate);
    const query = params.toString();
    try {
      return await fetchApi<ListingsBetweenDatesData>(
        `/analytics/listings-between-dates${query ? `?${query}` : ''}`
      );
    } catch (err) {
      if (err instanceof ApiError && err.status === 422) {
        throw new Error('La période sélectionnée ne peut pas dépasser 366 jours.');
      }
      throw err;
    }
  },

  async getTotalListingsValue(): Promise<TotalListingsValueData> {
    return fetchApi<TotalListingsValueData>('/analytics/total-value');
  },

  async getAverageListingPrice(): Promise<AverageListingPriceData> {
    return fetchApi<AverageListingPriceData>('/analytics/average-price');
  },

  async getTopLikedListings(): Promise<TopLikedListingsData> {
    return fetchApi<TopLikedListingsData>('/analytics/top-liked');
  },
};
