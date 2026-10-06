// Wire format of /api/ws, mirrored from backend/src/app/core/realtime/protocol.py.
// JSON text frames. The server rejects unknown fields and does not coerce
// types ("1" is not a number), so only send what is declared here.

// A subscription key. `id` is omitted for global kinds (e.g. presence).
export interface Topic {
  kind: string;
  id?: string | null;
}

// ── client -> server ────────────────────────────────────────────

export interface SubscribeFrame {
  type: "subscribe";
  topic_kind: string;
  topic_id?: string;
}

export interface UnsubscribeFrame {
  type: "unsubscribe";
  topic_kind: string;
  topic_id?: string;
}

// First frame only: reattach a session after a drop.
export interface ResumeFrame {
  type: "resume";
  session: string;
  last_seq: number;
}

export interface PingFrame {
  type: "ping";
}

// A business action. `ref` is echoed back in any error about it.
export interface MessageFrame {
  type: string;
  topic_kind: string;
  topic_id?: string;
  ref?: string;
  payload?: Record<string, unknown>;
}

export type ClientFrame =
  | SubscribeFrame
  | UnsubscribeFrame
  | ResumeFrame
  | PingFrame
  | MessageFrame;

// ── server -> client ────────────────────────────────────────────

// Always the first frame the server sends.
export interface SessionFrame {
  type: "session";
  session: string;
  resumed: boolean;
  // resumed: first seq of the replay that follows
  from_seq?: number;
  // not resumed: why a fresh stream started
  reason?: "new" | "expired" | "gap";
}

export type ErrorCode =
  | "forbidden"
  | "unknown_topic"
  | "unknown_type"
  | "rate_limited"
  | "too_many_topics"
  | "bad_request";

// An error never closes the connection.
export interface ErrorFrame {
  type: "error";
  code: ErrorCode;
  topic_kind?: string;
  topic_id?: string;
  ref?: string;
  detail?: string;
}

export interface PongFrame {
  type: "pong";
  ts: string;
}

// A business event. `seq` counts every event of the session: 1, 2, 3...
export interface RealtimeEvent<P = Record<string, unknown>> {
  type: string;
  topic_kind: string;
  topic_id?: string;
  payload: P;
  seq: number;
  ts: string;
}

export type ServerFrame = SessionFrame | ErrorFrame | PongFrame | RealtimeEvent;

// ── close codes ─────────────────────────────────────────────────

export const CloseCode = {
  NORMAL: 1000,
  GOING_AWAY: 1001, // idle, server restart: reconnect and resume
  ABNORMAL: 1006, // set by the browser: network loss, or handshake refused (403)
  POLICY_VIOLATION: 1008, // no handshake, or the login expired: log in again
  MESSAGE_TOO_BIG: 1009,
  INTERNAL_ERROR: 1011,
  TRY_AGAIN_LATER: 1013, // queue overflow ("gap") or too many sessions
  REPLACED: 4000, // another tab/socket resumed this session: do not reconnect
  REAUTH: 4001,
} as const;

// ── helpers ─────────────────────────────────────────────────────

export function topicKey(topic: Topic): string {
  return topic.id == null ? topic.kind : `${topic.kind}:${topic.id}`;
}

export function topicOf(frame: { topic_kind: string; topic_id?: string }): Topic {
  return { kind: frame.topic_kind, id: frame.topic_id ?? null };
}

export function topicFields(topic: Topic): { topic_kind: string; topic_id?: string } {
  return topic.id == null
    ? { topic_kind: topic.kind }
    : { topic_kind: topic.kind, topic_id: topic.id };
}

const CONTROL_TYPES = new Set(["session", "error", "pong"]);

function isObject(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

// Parse a server frame. Returns null on anything malformed rather than
// throwing: a bad frame must not take the connection down.
export function parseServerFrame(raw: unknown): ServerFrame | null {
  if (typeof raw !== "string") return null;
  let data: unknown;
  try {
    data = JSON.parse(raw);
  } catch {
    return null;
  }
  if (!isObject(data) || typeof data.type !== "string") return null;

  switch (data.type) {
    case "session":
      return typeof data.session === "string" && typeof data.resumed === "boolean"
        ? (data as unknown as SessionFrame)
        : null;
    case "error":
      return typeof data.code === "string" ? (data as unknown as ErrorFrame) : null;
    case "pong":
      return data as unknown as PongFrame;
    default:
      if (CONTROL_TYPES.has(data.type)) return null;
      return typeof data.topic_kind === "string" &&
        typeof data.seq === "number" &&
        isObject(data.payload)
        ? (data as unknown as RealtimeEvent)
        : null;
  }
}
