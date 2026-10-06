import type { Conversation, Message } from './message';
import type { Listing } from './listing';
import type { PublicUser, User } from './user';

/**
 * Target entity type for a report (`reports` table in schema.md)
 */
export type ReportTargetType ='listing' | 'message' | 'user' | 'review';

/**
 * Moderation report status (`reports` table in schema.md)
 */
export type ReportStatus = 'open' | 'closed' | 'in_progress' | 'resolved' | (string & {});

/**
 * Review left by a user after a transaction (`reviews` table in schema.md)
 */
export interface Review {
  id: string;
  conversation_id: string;
  author_id: string;
  subject_id: string;
  rating: number; // smallint (1 to 5)
  body: string;
  created_at: string;
  edited_at?: string | null;
  deleted_at?: string | null;

  // Optional relations after joins
  author?: PublicUser;
  subject?: PublicUser;
  conversation?: Conversation;
}

/**
 * Moderation report (`reports` table in schema.md)
 */
export interface Report {
  id: string;
  reporter_id: string;
  target_type: ReportTargetType;
  target_id: string;
  reason: string;
  status: ReportStatus;
  created_at: string;
  closed_at?: string | null;

  // Optional relations after joins
  reporter?: PublicUser;
  target?: Listing | Message | User | Review | PublicUser;
}

/**
 * DTO for creating a report
 */
export interface CreateReportInput {
  target_type: ReportTargetType;
  target_id: string;
  reason: string;
}

/**
 * DTO for creating a review
 */
export interface CreateReviewInput {
  conversation_id: string;
  subject_id: string;
  rating: number;
  body: string;
}
