/**
 * Centralized export of all types for the Lebon42 project
 * Based on database schema schema.md
 */

// User, OAuth, blocks, and friendship types
export * from './user';

// Listing, category, attribute, location, image, favorite, and search types
export * from './listing';

// Conversation, participant, listing message, and friend message types
export * from './message';

// Moderation report and review/rating types
export * from './report';

// Analytics types
export * from './analytics';

// User personal stats types
export * from './stats';

// Generic utility types for APIs and pagination
export interface PaginatedResponse<T> {
  data: T[];
  total: number;
  page: number;
  limit: number;
  total_pages: number;
}
