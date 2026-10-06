import type { Listing } from './listing';
import type { Review } from './report';

/**
 * Available roles for a user in Lebon42
 */
export type UserRole = 'admin' | 'moderator' | 'user';

/**
 * Statuses of a friendship as the UI shows it. 'blocked' is display-only: the
 * API never returns it, blocking someone deletes the friendship.
 */
export type FriendshipStatus = 'pending' | 'accepted' | 'blocked'

/**
 * Real-time presence status of a user.
 */
export type PresenceStatus = 'online' | 'offline';

/**
 * Push event received when a user connects or disconnects.
 */
export interface PresenceUpdate {
  user_id: string;
  status: PresenceStatus;
}

/**
 * Full User entity (`users` table in schema.md)
 */
export interface User {
  id: string;
  public_id: string;
  email: string;
  password_hash?: string | null;
  display_name: string;
  role: UserRole;
  bio?: string | null;
  is_active: boolean;
  avatar_path?: string | null;
  locale: string;
  totp_secret_encrypted?: string | null;
  totp_secret?: string | null; // Compatibility alias
  totp_enabled: boolean;
  rating: number;
  rating_count: number;
  email_verified_at?: string | null;
  deleted_at?: string | null;
  created_at?: string;
  updated_at?: string;
}

/**
 * Public user representation without sensitive data (password, TOTP secret)
 */
export interface PublicUser {
  id: string;
  public_id: string;
  display_name: string;
  role: UserRole;
  avatar_path?: string | null;
  bio?: string | null;
  rating: number;
  rating_count: number;
  is_active?: boolean;
}

/**
 * Admin user view representation returned by GET /users
 */
export interface AdminUser {
  public_id: string;
  display_name: string;
  role: UserRole;
  is_active: boolean;
  created_at: string;
  deleted_at?: string | null;
}

export interface AdminUserFilterParams {
  page?: number;
  limit?: number;
  q?: string;
  role?: string;
}

/**
 * Comprehensive user profile with statistics and relations
 */
export interface UserProfile extends PublicUser {
  email?: string;
  locale?: string;
  created_at?: string;
  listings_count?: number;
  liked_listings_count?: number;
  friends_count?: number;
  reviews_count?: number;
  reviews?: Review[];
  recent_listings?: Listing[];
  liked_listings?: Listing[];
  friends?: PublicUser[];
  /** Set by GET /users/{public_id}: this user blocked the viewer (one way only). */
  has_blocked_me?: boolean;
  /** True when the account has a password (email/password sign-in available). */
  has_password?: boolean;
}

/**
 * Friendship relation between two users (`friends` table in schema.md)
 */
export interface Friend {
  id: string;
  requester_id: string;
  address_id: string; // Column name from schema (recipient of the friend request)
  addressee_id?: string; // Convenient alias
  status: FriendshipStatus;
  created_at: string;
  responded_at?: string | null;
  requester?: PublicUser;
  addressee?: PublicUser;
}

/**
 * DTO for updating user profile information
 */
export interface UpdateUserInput {
  display_name?: string;
  bio?: string | null;
  avatar_path?: string | null;
  locale?: string;
  is_active?: boolean;
}
