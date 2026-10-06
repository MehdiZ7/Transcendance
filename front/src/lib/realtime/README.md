# `lib/realtime` — Client-Side Real-Time

A single WebSocket per browser tab to `/api/ws`, authenticated by the HTTP session cookie (no token parameters required). The client manages connection lifecycle, reconnects, stream resumption, resubscriptions, and close codes: feature code only interacts with **topics** and **events**.

Server-side protocol specifications and rules: `backend/src/app/core/realtime/README.md`.

| File | Role |
|---|---|
| `protocol.ts` | Frame types (mirror of `protocol.py`), close codes, `topicKey` helpers... |
| `client.ts` | `RealtimeClient`: connection management and its complete lifecycle |
| `index.ts` | Tab-singleton client (`getRealtime`) and the shared auth check |
| `hooks.ts` | React Hooks: `useRealtimeTopic`, `useRealtimeStatus`, `useRealtimeSend` |
| `topics.ts` | Application topics and payload types (mirror of `app/realtime_topics.py`) |

During server-side rendering (SSR), `getRealtime()` returns `null` and hooks perform no operations.

## Application Topics

Declared server-side in `backend/src/app/realtime_topics.py` and typed on the client in `topics.ts`. User identifiers are always `public_id` (the `id` field of `PublicUser` returned by the REST API).

| Topic | Who Can Subscribe | Events |
|---|---|---|
| `user:<public_id>` (`userTopic(id)`) | Owner only | `message.created`, `typing`, `friend_message.created`, `friend_typing` |
| `presence` (`PRESENCE_TOPIC`) | Any authenticated user | `presence.snapshot`, `presence.changed` |

| Event | Payload | When |
|---|---|---|
| `message.created` | A `Message` object (same structure as `POST /conversations/{id}/messages`) | Broadcast to **both** participants after message creation: the sender's other tabs also receive it; deduplicate by `id`. |
| `typing` | `{conversation_id: number, user_id, is_typing: boolean}` | Relays the `typing` client event of the other participant. |
| `friend_message.created` | Direct friend message (same structure as `POST /friends/{public_id}/messages`, with `friend_id`) | Broadcast to **both** friends after sending: deduplicate by `id`, separately from listing messages. |
| `friend_typing` | `{friend_id: number, user_id, is_typing: boolean}` | Relays the `friend_typing` client event of the other friend. |
| `presence.snapshot` | `{online: string[]}` | Dispatched immediately upon subscription (and after resubscription): full list of online users; omitted users are offline. |
| `presence.changed` | `{user_id, status: "online" \| "offline"}` | Dispatched on first socket open / last socket close for a given user. |

Client Messages:

| Type | Target Topic | Payload |
|---|---|---|
| `typing` | Sender's own `user:<public_id>` | `{conversation_id: number, is_typing: boolean}` |
| `friend_typing` | Sender's own `user:<public_id>` | `{friend_id: number, is_typing: boolean}` |

The server validates that the sender participates in the conversation, then relays the event to the other participant; otherwise, the frame is silently dropped. Malformed payloads return a `bad_request` error. `useMessages` sends `true` at most every 1.5s while typing, and `false` after 2s of inactivity. As with sending messages, `typing` is not relayed if the conversation is closed or if either user has blocked the other.

`friend_typing` follows the same rules for friends: relayed only if the friendship is accepted, the sender is a member, and neither party has blocked the other. `friend_id` matches the ID returned by `GET /friends/messages`. Note that friendship and conversation IDs overlap (as do the IDs of the two message tables): hence the distinct `friend_*` event names to avoid cross-domain collisions on the frontend.

User presence intentionally ignores block lists: all connected users can see who is online, including users they have blocked. This is an intentional design decision documented in `backend/src/app/realtime_topics.py`.

"Online" denotes "at least one active real-time WebSocket connection", not "issued an HTTP request recently" (which is tracked by `GET /analytics/online-students`).

Usage: `hooks/useMessages.ts` (unified inbox: listing conversations via `message.created`/`typing`, friend conversations via `friend_message.created`/`friend_typing`), `lib/api/presence.ts` → `hooks/usePresence.ts` (online status dot).

On the client, both message types are unified inside `useMessages`: active thread keys are formatted as `"listing:<id>"` or `"friend:<id>"` (since database IDs overlap), and friend messages reuse the same `ChatWindow`/`MessageBubble` UI components.

## Subscribing to Topic Events

```tsx
"use client";
import { useState } from "react";
import { useRealtimeTopic } from "@/lib/realtime/hooks";
import { userTopic } from "@/lib/realtime/topics";

function Conversation({ me, conversationId }: { me: string | null; conversationId: string }) {
  const [messages, setMessages] = useState<Message[]>([]);
  const reload = () => getMessages(conversationId).then(setMessages); // HTTP fallback

  useRealtimeTopic<Message>(
    me ? userTopic(me) : null, // null until the current user's public_id is known
    (event) => {
      if (event.type !== "message.created" || event.payload.conversation_id !== conversationId) return;
      // Skip if the REST response already appended it
      setMessages((m) => m.some((x) => x.id === event.payload.id) ? m : [...m, event.payload]);
    },
    {
      onReset: reload, // Events may have been missed: reload via HTTP
      onError: (e) => console.warn("rejected", e.code), // forbidden, unknown_topic, too_many_topics, rate_limited
    },
  );
  // ...
}
```

- The hook subscribes on mount and unsubscribes on unmount. Multiple components listening to the same topic share a single server subscription.
- A `null` topic disables subscription (e.g. while an ID is still loading).
- Event handler references can change on each render without triggering resubscription.
- The WebSocket connection establishes automatically on the first subscription.
- If a subscription is rejected by the server, it is removed and `onError` is called. No automatic retry is performed: retry logic is left to the component.

**Always fetch initial state via HTTP**, then apply incoming real-time events on top. Real-time transports changes only.

## Sending an Action

```tsx
const send = useRealtimeSend();
// Client messages go on the sender's own topic; the server relays them.
send("typing", userTopic(me), { conversation_id: Number(conversationId), is_typing: true }, {
  onError: (e) => console.warn(e.code, e.detail),
});
```

No delivery acknowledgments: effects return as broadcast events, failures invoke `onError`. When offline, outgoing messages are queued in memory (up to 50) and flushed upon reconnection. Messages exceeding 4 KB are rejected locally to avoid server-side socket termination.

For critical state changes (sending a message, publishing a listing), use the REST API: the backend route commits and publishes the event. The broadcast event is also sent back to the sender (for multi-tab synchronization) and often arrives **before** the HTTP response: only append if not already in the list on both ends (see `hooks/useMessages.ts`). On failure, do not show a phantom message: restore the unsent text to the input field and display an error.

## Connection Status

```tsx
const status = useRealtimeStatus();
// "idle" | "connecting" | "open" | "reconnecting" | "unauthorized" | "replaced" | "closed"
```

## Connecting and Disconnecting

The connection is created lazily on the first subscription (`getRealtime()`). A full page reload, including after login or logout, tears it down and starts a fresh one.

## Built-In Client Behaviors

| Situation | Behavior |
|---|---|
| Network interruption, server restart (1001, 1006, 1011, 1012) | Reconnects with exponential backoff (0.5s → 30s with jitter), then sends `resume`. |
| Resumption accepted | Missed events are replayed in order; duplicate event IDs are skipped. |
| Resumption rejected (expired session, gap in stream) | Fresh stream: resubscribes to all active topics, invokes `onReset`. |
| Unauthenticated, `Origin` rejected (handshake 403) | Checks `/users/me`: if not 200 (a 204 means anonymous), transitions to `unauthorized` and stops retrying. |
| Expired session, logged out remotely, or account suspended (4001) | Checks `/users/me`: if not 200 (a 204 means anonymous), transitions to `unauthorized` and halts (a fresh page load after login recreates the client); otherwise reconnects with fresh stream and calls `onReset`. |
| No initial frame within 10s (1008) | Transitions to `unauthorized`, halts. |
| Server capacity reached, queue full (1013) | Reconnects with backoff. |
| Session resumed by another socket (4000) | Transitions to `replaced`, halts: reconnecting would cause duplicate stealing loops. |
| No incoming data for 2 heartbeats (50s) | Dead link: abandons dead socket, triggers reconnect and resume. |
| Application `ping` | Sent every 25s (`ws_heartbeat_interval`). |
| Over 1000 frames in 10s per user (`ws_rate_limit_per_10s`) | `rate_limited` error: routed by `ref` for actions, by topic for subscriptions (removed). |

The session token remains **in memory**: it survives brief connection drops and client-side page transitions, but not a full page reload. A full reload re-fetches state via HTTP anyway, and resuming would mistakenly restore stale subscriptions from the previous view.

## Usage Outside React

```ts
import { getRealtime } from "@/lib/realtime";

const client = getRealtime();
const unsubscribe = client?.subscribe({ kind: "presence" }, {
  onEvent: (event) => { /* ... */ },
});
client?.onAnyEvent((event) => { /* notifications, debug */ });
```

`RealtimeClient` accepts an injectable `createSocket` factory: this enables programmatic control in Node.js environments or headless tests without a browser.
