"use client";

import { useEffect, useEffectEvent, useSyncExternalStore } from "react";
import type { RealtimeClient, RealtimeStatus, SendOptions, TopicHandlers } from "./client";
import { getRealtime } from "./index";
import type { ErrorFrame, RealtimeEvent, Topic } from "./protocol";
import { topicKey } from "./protocol";

const noop = () => {};

// The tab's client, or null during server rendering.
export function useRealtime(): RealtimeClient | null {
  return getRealtime();
}

// "idle" | "connecting" | "open" | "reconnecting" | "unauthorized" | "replaced" | "closed"
export function useRealtimeStatus(): RealtimeStatus {
  return useSyncExternalStore(
    (onChange) => getRealtime()?.onStatus(onChange) ?? noop,
    () => getRealtime()?.getStatus() ?? "idle",
    () => "idle",
  );
}

export interface TopicOptions {
  onError?: (error: ErrorFrame) => void;
  onReset?: () => void;
}

// Receive the events of one topic while the component is mounted.
// `topic` null = not subscribed (e.g. until an id is known). The handlers
// may change on every render without resubscribing.
//
//   useRealtimeTopic({ kind: "conversation", id }, (event) => {
//     if (event.type === "message.created") setMessages((m) => [...m, event.payload]);
//   }, { onReset: refetch });
export function useRealtimeTopic<P = Record<string, unknown>>(
  topic: Topic | null,
  onEvent: (event: RealtimeEvent<P>) => void,
  options: TopicOptions = {},
): void {
  const key = topic ? topicKey(topic) : null;
  const kind = topic?.kind;
  const id = topic?.id ?? null;
  const handleEvent = useEffectEvent(onEvent);
  const handleError = useEffectEvent((error: ErrorFrame) => options.onError?.(error));
  const handleReset = useEffectEvent(() => options.onReset?.());

  useEffect(() => {
    const client = getRealtime();
    if (!client || key === null || kind === undefined) return;
    const handlers: TopicHandlers<P> = {
      onEvent: (event) => handleEvent(event),
      onError: (error) => handleError(error),
      onReset: () => handleReset(),
    };
    return client.subscribe<P>({ kind, id }, handlers);
  }, [key, kind, id]);
}

function sendRealtime(
  type: string,
  topic: Topic,
  payload?: Record<string, unknown>,
  options?: SendOptions,
): string | null {
  return getRealtime()?.send(type, topic, payload, options) ?? null;
}

// Send a business message on a topic; returns its ref, or null without a
// client. The function is stable: safe in effect dependencies.
export function useRealtimeSend(): typeof sendRealtime {
  return sendRealtime;
}
