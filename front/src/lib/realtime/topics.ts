// The app's topics and event payloads, mirrored from
// backend/src/app/realtime_topics.py. See README.md, "Topics de l'app".

import type { Message, FriendMessage } from "@/types/message";
import type { PresenceStatus } from "@/types/user";
import type { Topic } from "./protocol";

// Personal topic: only its owner may subscribe. `id` is the user's public_id.
export function userTopic(publicId: string): Topic {
  return { kind: "user", id: publicId };
}

export const PRESENCE_TOPIC: Topic = { kind: "presence" };

// ── on user:<public_id> ─────────────────────────────────────────

// "message.created": a message was sent in one of the user's conversations,
// by anyone, the user included (their other tabs need it too).
export type MessageCreatedPayload = Message;

// "typing": the other participant started or stopped typing.
export interface TypingPayload {
  conversation_id: number;
  user_id: string;
  is_typing: boolean;
}

// "friend_message.created": a direct message between friends, sent to both
export type FriendMessageCreatedPayload = FriendMessage;

// "friend_typing": the other friend started or stopped typing.
export interface FriendTypingPayload {
  friend_id: number;
  user_id: string;
  is_typing: boolean;
}

// ── on presence ─────────────────────────────────────────────────

// "presence.snapshot": sent right after subscribing, every connected user.
export interface PresenceSnapshotPayload {
  online: string[];
}

// "presence.changed": a user's first socket opened, or their last one closed.
export interface PresenceChangedPayload {
  user_id: string;
  status: PresenceStatus;
}
