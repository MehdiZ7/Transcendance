// One WebSocket per tab to /api/ws, kept alive across drops.
//
// What this class takes care of, so features only deal with topics and events:
// - the handshake (first frame: `resume` when a session exists, else `ping`);
// - reconnecting with backoff, then resuming: missed events are replayed;
// - re-subscribing when the server starts a fresh stream, and telling the
//   features (onReset) that events may have been missed;
// - reference-counted subscriptions: many components, one server subscription;
// - dropping duplicates and detecting holes through `seq`;
// - the application heartbeat and dead-link detection;
// - what each close code means (stop, log in again, retry later...).
//
// The socket authenticates with the session cookie: nothing to pass here.

import {
  CloseCode,
  type ClientFrame,
  type ErrorFrame,
  type MessageFrame,
  type RealtimeEvent,
  type SessionFrame,
  type Topic,
  parseServerFrame,
  topicFields,
  topicKey,
  topicOf,
} from "./protocol";
import { logError } from "@/lib/log";

export type RealtimeStatus =
  | "idle" // never started
  | "connecting" // first connection in progress
  | "open" // session established, events flowing
  | "reconnecting" // lost, retrying with backoff
  | "unauthorized" // not logged in (or the login expired): call reconnect() after login
  | "replaced" // this session was resumed by another socket: stopped on purpose
  | "closed"; // disconnect() was called

// The subset of the browser WebSocket this client uses (injectable for tests).
export interface SocketLike {
  readonly readyState: number;
  send(data: string): void;
  close(code?: number, reason?: string): void;
  onopen: ((ev: Event) => unknown) | null;
  onmessage: ((ev: MessageEvent) => unknown) | null;
  onclose: ((ev: CloseEvent) => unknown) | null;
  onerror: ((ev: Event) => unknown) | null;
}

export interface RealtimeOptions {
  // Defaults to ws(s)://<current host>/api/ws
  url?: string;
  createSocket?: (url: string) => SocketLike;
  // Called when a handshake fails before opening (the browser hides the
  // 403): resolve false when the user is logged out, to stop retrying.
  checkAuth?: () => Promise<boolean>;
  // Connect on the first subscribe/send instead of waiting for connect()
  autoConnect?: boolean;
  // Must stay below the server's ws_session_ttl (60s): ws_heartbeat_interval
  heartbeatMs?: number;
  backoffBaseMs?: number;
  backoffMaxMs?: number;
  // Business messages kept while disconnected, sent once the session is back
  maxQueued?: number;
  // Server limit ws_max_frame_bytes: a bigger frame would close the socket
  maxFrameBytes?: number;
}

export interface TopicHandlers<P = Record<string, unknown>> {
  onEvent: (event: RealtimeEvent<P>) => void;
  // forbidden / unknown_topic / too_many_topics: the subscription is dropped
  onError?: (error: ErrorFrame) => void;
  // Events may have been missed (fresh stream after a drop): reload over HTTP
  onReset?: () => void;
}

export interface SendOptions {
  // Called if the server answers with an error about this message
  onError?: (error: ErrorFrame) => void;
}

interface Subscription {
  topic: Topic;
  handlers: Set<TopicHandlers<never>>;
}

type Listener<T> = (value: T) => void;

const OPEN = 1;
const REF_TTL_MS = 30_000;

function defaultUrl(): string {
  const { protocol, host } = window.location;
  return `${protocol === "https:" ? "wss:" : "ws:"}//${host}/api/ws`;
}

function localError(detail: string, ref?: string): ErrorFrame {
  return { type: "error", code: "bad_request", detail, ref };
}

export class RealtimeClient {
  private readonly opts: Required<Omit<RealtimeOptions, "url" | "checkAuth">> &
    Pick<RealtimeOptions, "url" | "checkAuth">;

  private socket: SocketLike | null = null;
  private status: RealtimeStatus = "idle";
  private stopped = true;
  private ready = false; // the session frame arrived on the current socket
  private everOpened = false;

  private token: string | null = null;
  private lastSeq = 0;
  private attempts = 0;
  private lastSeen = 0;

  private readonly subs = new Map<string, Subscription>();
  // What the server holds for our session, as far as we know
  private readonly serverTopics = new Map<string, Topic>();
  private readonly queue: MessageFrame[] = [];
  private readonly refs = new Map<string, { onError: Listener<ErrorFrame>; at: number }>();
  private refCounter = 0;

  private reconnectTimer: ReturnType<typeof setTimeout> | null = null;
  private heartbeatTimer: ReturnType<typeof setInterval> | null = null;

  private readonly statusListeners = new Set<Listener<RealtimeStatus>>();
  private readonly resetListeners = new Set<Listener<SessionFrame>>();
  private readonly errorListeners = new Set<Listener<ErrorFrame>>();
  private readonly eventListeners = new Set<Listener<RealtimeEvent>>();

  constructor(options: RealtimeOptions = {}) {
    this.opts = {
      url: options.url,
      checkAuth: options.checkAuth,
      createSocket: options.createSocket ?? ((url) => new WebSocket(url)),
      autoConnect: options.autoConnect ?? true,
      heartbeatMs: options.heartbeatMs ?? 25_000,
      backoffBaseMs: options.backoffBaseMs ?? 500,
      backoffMaxMs: options.backoffMaxMs ?? 30_000,
      maxQueued: options.maxQueued ?? 50,
      maxFrameBytes: options.maxFrameBytes ?? 4096,
    };
  }

  // ── lifecycle ────────────────────────────────────────────────

  getStatus(): RealtimeStatus {
    return this.status;
  }

  // Start (no-op when already running). Does not restart after
  // "unauthorized" or "replaced": use reconnect() for that.
  connect(): void {
    if (!this.stopped) return;
    if (this.status === "unauthorized" || this.status === "replaced") return;
    this.stopped = false;
    this.openSocket();
  }

  // Start again whatever the state, e.g. right after a login.
  reconnect(): void {
    this.stopped = false;
    this.attempts = 0;
    this.clearReconnect();
    if (this.socket) this.dropSocket(CloseCode.NORMAL);
    this.openSocket();
  }

  // Stop for good (logout, page teardown). Subscriptions are kept locally
  // and re-sent if the client is started again.
  disconnect(): void {
    this.stopped = true;
    this.clearReconnect();
    this.forgetSession();
    if (this.socket) this.dropSocket(CloseCode.NORMAL);
    this.setStatus("closed");
  }

  // ── subscriptions and messages ───────────────────────────────

  // Returns the function that unsubscribes this handler.
  subscribe<P = Record<string, unknown>>(topic: Topic, handlers: TopicHandlers<P>): () => void {
    const key = topicKey(topic);
    let sub = this.subs.get(key);
    if (!sub) {
      sub = { topic: { kind: topic.kind, id: topic.id ?? null }, handlers: new Set() };
      this.subs.set(key, sub);
    }
    const entry = handlers as TopicHandlers<never>;
    sub.handlers.add(entry);
    if (this.ready && !this.serverTopics.has(key)) this.sendSubscribe(sub.topic);
    this.maybeAutoConnect();

    return () => {
      const current = this.subs.get(key);
      if (!current || !current.handlers.delete(entry) || current.handlers.size > 0) return;
      this.subs.delete(key);
      if (this.ready && this.serverTopics.has(key)) this.sendUnsubscribe(current.topic);
    };
  }

  // Send a business message; returns its `ref`. There is no acknowledgement:
  // the effect arrives as an event, a failure as onError.
  send(type: string, topic: Topic, payload: Record<string, unknown> = {}, options: SendOptions = {}): string {
    const ref = `c-${++this.refCounter}`;
    const frame: MessageFrame = { type, ...topicFields(topic), ref, payload };
    if (!this.fits(frame)) {
      options.onError?.(localError("message too big", ref));
      return ref;
    }
    if (options.onError) {
      this.pruneRefs();
      this.refs.set(ref, { onError: options.onError, at: Date.now() });
    }
    if (this.ready) {
      this.sendFrame(frame);
    } else if (this.queue.length < this.opts.maxQueued) {
      this.queue.push(frame);
      this.maybeAutoConnect();
    } else {
      this.refs.delete(ref);
      options.onError?.(localError("not connected", ref));
    }
    return ref;
  }

  // ── listeners (each returns its unsubscribe function) ─────────

  onStatus(listener: Listener<RealtimeStatus>): () => void {
    return this.listen(this.statusListeners, listener);
  }

  // A fresh stream replaced a lost one: every topic may have missed events.
  onReset(listener: Listener<SessionFrame>): () => void {
    return this.listen(this.resetListeners, listener);
  }

  // Every error frame, including the ones already routed to a handler.
  onError(listener: Listener<ErrorFrame>): () => void {
    return this.listen(this.errorListeners, listener);
  }

  // Every event, whatever the topic (notifications, debugging).
  onAnyEvent(listener: Listener<RealtimeEvent>): () => void {
    return this.listen(this.eventListeners, listener);
  }

  // ── socket ───────────────────────────────────────────────────

  private openSocket(): void {
    this.setStatus(this.everOpened || this.attempts > 0 ? "reconnecting" : "connecting");
    let socket: SocketLike;
    try {
      socket = this.opts.createSocket(this.opts.url ?? defaultUrl());
    } catch {
      this.scheduleReconnect();
      return;
    }
    this.socket = socket;
    this.ready = false;
    let opened = false;

    socket.onopen = () => {
      opened = true;
      this.lastSeen = Date.now();
      // The server waits for a first frame before opening the session
      this.sendFrame(
        this.token ? { type: "resume", session: this.token, last_seq: this.lastSeq } : { type: "ping" },
      );
      this.startHeartbeat();
    };
    socket.onmessage = (ev) => {
      if (this.socket === socket) this.handleRaw(ev.data);
    };
    socket.onclose = (ev) => {
      if (this.socket !== socket) return; // already dropped on purpose
      this.socket = null;
      this.handleClose(ev.code, opened);
    };
    socket.onerror = () => {
      // Once open, a close event follows. Before open (refused handshake,
      // unreachable server) some runtimes never send one: settle it here,
      // the late close, if any, is ignored since this.socket moved on.
      if (opened || this.socket !== socket) return;
      this.socket = null;
      this.handleClose(CloseCode.ABNORMAL, false);
    };
  }

  // Detach the socket first, so its late close event is ignored.
  // `code` must be 1000 or 3000-4999: the browser throws on any other
  // (1001 included), and the socket would stay open. The server detaches
  // the session whatever the code, so it stays resumable.
  private dropSocket(code: number): void {
    const socket = this.socket;
    this.socket = null;
    this.ready = false;
    this.stopHeartbeat();
    if (!socket) return;
    socket.onopen = socket.onmessage = socket.onclose = socket.onerror = null;
    try {
      socket.close(code);
    } catch {
      // already closing
    }
  }

  private handleClose(code: number, opened: boolean): void {
    this.ready = false;
    this.stopHeartbeat();
    if (this.stopped) return this.setStatus("closed");

    switch (code) {
      case CloseCode.NORMAL:
        // The server ends a session normally only when it wants us gone
        this.stopped = true;
        return this.setStatus("closed");
      case CloseCode.REPLACED:
        // Reconnecting would steal the session back, forever
        this.stopped = true;
        return this.setStatus("replaced");
      case CloseCode.POLICY_VIOLATION:
        return this.unauthorized();
    }

    // Refused handshake (1006, same as a lost network), or a session closed
    // server side / an expired login (4001): ask whether we are logged in
    if ((!opened || code === CloseCode.REAUTH) && this.opts.checkAuth) {
      this.opts.checkAuth().then(
        (loggedIn) => {
          if (this.stopped || this.socket) return;
          if (loggedIn) this.scheduleReconnect();
          else this.unauthorized();
        },
        () => {
          if (!this.stopped && !this.socket) this.scheduleReconnect();
        },
      );
      this.setStatus("reconnecting");
      return;
    }
    this.scheduleReconnect();
  }

  private unauthorized(): void {
    this.stopped = true;
    this.clearReconnect();
    this.forgetSession();
    this.setStatus("unauthorized");
  }

  private forgetSession(): void {
    this.token = null;
    this.lastSeq = 0;
    this.serverTopics.clear();
  }

  private scheduleReconnect(): void {
    if (this.stopped) return;
    this.clearReconnect();
    this.attempts += 1;
    const exp = this.opts.backoffBaseMs * 2 ** Math.min(this.attempts - 1, 16);
    const delay = Math.min(this.opts.backoffMaxMs, exp) * (0.5 + Math.random() / 2);
    this.setStatus("reconnecting");
    this.reconnectTimer = setTimeout(() => {
      this.reconnectTimer = null;
      if (!this.stopped) this.openSocket();
    }, delay);
  }

  private clearReconnect(): void {
    if (this.reconnectTimer !== null) clearTimeout(this.reconnectTimer);
    this.reconnectTimer = null;
  }

  private maybeAutoConnect(): void {
    if (this.opts.autoConnect && this.status === "idle") this.connect();
  }

  // ── heartbeat ────────────────────────────────────────────────

  private startHeartbeat(): void {
    this.stopHeartbeat();
    this.heartbeatTimer = setInterval(() => {
      if (Date.now() - this.lastSeen > 2 * this.opts.heartbeatMs) {
        // Nothing heard for two periods: the link is dead even if TCP
        // has not noticed. Drop it and resume on a new socket.
        this.dropSocket(CloseCode.NORMAL);
        this.scheduleReconnect();
        return;
      }
      if (this.ready) this.sendFrame({ type: "ping" });
    }, this.opts.heartbeatMs);
  }

  private stopHeartbeat(): void {
    if (this.heartbeatTimer !== null) clearInterval(this.heartbeatTimer);
    this.heartbeatTimer = null;
  }

  // ── inbound ──────────────────────────────────────────────────

  private handleRaw(raw: unknown): void {
    this.lastSeen = Date.now();
    const frame = parseServerFrame(raw);
    if (!frame) return;
    switch (frame.type) {
      case "session":
        return this.handleSession(frame as SessionFrame);
      case "error":
        return this.handleError(frame as ErrorFrame);
      case "pong":
        return;
      default:
        return this.handleEvent(frame as RealtimeEvent);
    }
  }

  private handleSession(frame: SessionFrame): void {
    this.ready = true;
    this.attempts = 0;
    const lostStream = this.everOpened && !frame.resumed;
    this.everOpened = true;

    if (!frame.resumed) {
      this.token = frame.session;
      this.lastSeq = 0;
      this.serverTopics.clear();
    }
    // Resumed: the server kept our subscriptions; sync what changed offline
    for (const [key, topic] of [...this.serverTopics]) {
      if (!this.subs.has(key)) this.sendUnsubscribe(topic);
    }
    for (const [key, sub] of this.subs) {
      if (!this.serverTopics.has(key)) this.sendSubscribe(sub.topic);
    }
    for (const frameOut of this.queue.splice(0)) this.sendFrame(frameOut);
    this.setStatus("open");

    if (lostStream) {
      for (const listener of this.resetListeners) safely(listener, frame);
      for (const sub of this.subs.values()) {
        for (const h of sub.handlers) if (h.onReset) safely(h.onReset, undefined);
      }
    }
  }

  private handleEvent(event: RealtimeEvent): void {
    if (event.seq <= this.lastSeq) return; // replayed twice
    if (event.seq !== this.lastSeq + 1) {
      // A hole: never expected from the server. Start a fresh stream.
      this.forgetSession();
      this.dropSocket(CloseCode.NORMAL);
      this.scheduleReconnect();
      return;
    }
    this.lastSeq = event.seq;
    const sub = this.subs.get(topicKey(topicOf(event)));
    if (sub) for (const h of sub.handlers) safely(h.onEvent, event as never);
    for (const listener of this.eventListeners) safely(listener, event);
  }

  private handleError(error: ErrorFrame): void {
    const routed = error.ref ? this.refs.get(error.ref) : undefined;
    if (routed && error.ref) {
      this.refs.delete(error.ref);
      safely(routed.onError, error);
    } else if (!error.ref && error.topic_kind && isSubscribeRefusal(error)) {
      const key = topicKey(topicOf({ topic_kind: error.topic_kind, topic_id: error.topic_id }));
      const sub = this.subs.get(key);
      this.subs.delete(key);
      this.serverTopics.delete(key);
      if (sub) for (const h of sub.handlers) if (h.onError) safely(h.onError, error);
    }
    for (const listener of this.errorListeners) safely(listener, error);
  }

  // ── outbound ─────────────────────────────────────────────────

  private sendSubscribe(topic: Topic): void {
    this.serverTopics.set(topicKey(topic), topic);
    this.sendFrame({ type: "subscribe", ...topicFields(topic) });
  }

  private sendUnsubscribe(topic: Topic): void {
    this.serverTopics.delete(topicKey(topic));
    this.sendFrame({ type: "unsubscribe", ...topicFields(topic) });
  }

  private sendFrame(frame: ClientFrame): void {
    const socket = this.socket;
    if (!socket || socket.readyState !== OPEN) return;
    try {
      socket.send(JSON.stringify(frame));
    } catch {
      // the close event will follow
    }
  }

  private fits(frame: ClientFrame): boolean {
    return new TextEncoder().encode(JSON.stringify(frame)).length <= this.opts.maxFrameBytes;
  }

  private pruneRefs(): void {
    const limit = Date.now() - REF_TTL_MS;
    for (const [ref, entry] of this.refs) if (entry.at < limit) this.refs.delete(ref);
  }

  // ── listeners ────────────────────────────────────────────────

  private setStatus(status: RealtimeStatus): void {
    if (this.status === status) return;
    this.status = status;
    for (const listener of this.statusListeners) safely(listener, status);
  }

  private listen<T>(set: Set<Listener<T>>, listener: Listener<T>): () => void {
    set.add(listener);
    return () => {
      set.delete(listener);
    };
  }
}

function isSubscribeRefusal(error: ErrorFrame): boolean {
  return (
    error.code === "forbidden" ||
    error.code === "unknown_topic" ||
    error.code === "too_many_topics" ||
    error.code === "rate_limited"
  );
}

// A feature's handler must not break the socket loop.
function safely<T>(fn: (value: T) => void, value: T): void {
  try {
    fn(value);
  } catch (err) {
    logError("[realtime] handler failed", err);
  }
}
