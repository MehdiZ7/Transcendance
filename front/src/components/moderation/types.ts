import type { Report, Review } from '@/types/report';
import type { Listing } from '@/types/listing';
import type { Message } from '@/types/message';
import type { PublicUser } from '@/types/user';

export type ModerationTab = 'listings' | 'messages' | 'users' | 'reviews' | 'history' | 'admin-users';
export type HistoryTypeFilter = 'all' | 'listing' | 'message' | 'user' | 'review';
export type HistoryStatusFilter = 'all' | 'resolved' | 'closed';

export interface ModerationCounts {
  listings: number;
  messages: number;
  users: number;
  reviews: number;
  history: number;
}

export interface QueueConfig {
  emptyTitle: string;
  emptyDescription: string;
}

export function isReportTreated(report: Report): boolean {
  const status = report.status;
  return status === 'resolved' || status === 'closed' || Boolean(report.closed_at);
}

export function getTargetUser(report: Report | null): PublicUser | null {
  if (!report || !report.target) return null;
  const normType = report.target_type;
  if (normType === 'listing') {
    const listing = report.target as Listing;
    return listing.seller || null;
  }
  if (normType === 'message') {
    const message = report.target as Message;
    return message.sender || null;
  }
  if (normType === 'user') {
    return (report.target as PublicUser) || null;
  }
  if (normType === 'review') {
    const review = report.target as Review;
    return review.author || null;
  }
  return null;
}
