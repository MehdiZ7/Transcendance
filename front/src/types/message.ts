import type { Listing, ListingStatus } from './listing';
import type { PublicUser } from './user';

/**
 * Role of a participant in a listing conversation
 */
export type ConversationParticipantRole = 'buyer' | 'seller' | 'BUYER' | 'SELLER';

/**
 * Conversation participant (`conversation_participants` table in schema.md)
 */
export interface ConversationParticipant {
  conversation_id: string;
  user_id: string;
  role: ConversationParticipantRole;
  closed: boolean;
  user?: PublicUser;
}

/**
 * Message within a listing conversation (`messages` table in schema.md)
 */
export interface Message {
  id: string;
  conversation_id: string;
  sender_id: string;
  body: string;
  created_at: string;
  edited_at?: string | null;
  deleted_at?: string | null;
  sender?: PublicUser;
}

/**
 * Direct message between friends (`friends_messages` table in schema.md)
 */
export interface FriendMessage {
  id: string;
  friend_id: number; // Reference to friends(id)
  sender_id: string;
  body: string;
  created_at: string;
  edited_at?: string | null;
  deleted_at?: string | null;
  sender?: PublicUser;
}

/** Friend conversation summary for inbox display */
export interface FriendConversationSummary {
  type: 'friend';
  friend_id: number;
  other_participant: PublicUser;
  last_message: FriendMessage | null;
  unread_count: number;
  updated_at: string;
}

/**
 * Conversation tied to a listing (`conversations` table in schema.md)
 */
export interface Conversation {
  id: string;
  listing_id?: string | null;
  created_at?: string;
  updated_at?: string;
  listing?: Listing;
  participants?: ConversationParticipant[];
  messages?: Message[];
  last_message?: Message | null;
  unread_count?: number;
}

/**
 * Conversation summary for inbox display
 */
export interface ConversationSummary {
  id: string;
  listing_id?: string | null;
  listing_public_id?: string | null;
  listing_title?: string | null;
  listing_cover_image?: string | null;
  other_participant: PublicUser;
  last_message?: Message | null;
  unread_count: number;
  is_closed: boolean;
  updated_at: string;
  listing_status?: ListingStatus | null;
  listing_seller_id?: string | null;
  listing_buyer_id?: string | null;
  has_reviewed?: boolean;
}

/** A listing conversation or a friend conversation, in one inbox. */
export type InboxKind = 'listing' | 'friend';

export interface InboxConversation extends ConversationSummary {
  kind: InboxKind;
  rawId: string;
}