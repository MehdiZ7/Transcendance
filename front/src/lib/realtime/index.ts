// Realtime toolkit: one authenticated WebSocket per tab to /api/ws.
// See README.md in this folder.

import { getApiBaseUrl } from "@/lib/api/client";
import { RealtimeClient } from "./client";

export * from "./protocol";
export { RealtimeClient } from "./client";
export type { RealtimeOptions, RealtimeStatus, SendOptions, SocketLike, TopicHandlers } from "./client";

let client: RealtimeClient | null = null;

// false only when the API says we are logged out; a network error keeps
// the client retrying.
async function stillLoggedIn(): Promise<boolean> {
  try {
    const res = await fetch(`${getApiBaseUrl()}/users/me`, { credentials: "include" });
    // Anonymous is a 204 (not a 401): only a 200 means still logged in.
    return res.status === 200;
  } catch {
    return true;
  }
}

// The tab's client, created on first use. null during server rendering.
export function getRealtime(): RealtimeClient | null {
  if (typeof window === "undefined") return null;
  client ??= new RealtimeClient({ checkAuth: stillLoggedIn });
  return client;
}
