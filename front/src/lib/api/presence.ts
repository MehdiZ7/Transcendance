import type { PresenceStatus, PresenceUpdate } from "@/types";
import { getRealtime } from "@/lib/realtime";
import {
  PRESENCE_TOPIC,
  type PresenceChangedPayload,
  type PresenceSnapshotPayload,
} from "@/lib/realtime/topics";

export interface PresenceSource {
  getInitialStatus(): Record<string, PresenceStatus>;
  subscribe(onUpdate: (update: PresenceUpdate) => void): () => void;
}

function createWebSocketPresenceSource(): PresenceSource {
  const listeners = new Set<(update: PresenceUpdate) => void>();
  const statuses: Record<string, PresenceStatus> = {};
  let unsubscribe: (() => void) | null = null;

  const set = (user_id: string, status: PresenceStatus) => {
    if (statuses[user_id] === status) return;
    statuses[user_id] = status;
    listeners.forEach((l) => l({ user_id, status }));
  };

  // The snapshot is the whole truth: whoever is missing from it went offline
  // while we were not listening (first subscribe, or resubscribe after a reset).
  const applySnapshot = ({ online }: PresenceSnapshotPayload) => {
    const now = new Set(online);
    for (const user_id of Object.keys(statuses)) {
      if (!now.has(user_id)) set(user_id, "offline");
    }
    now.forEach((user_id) => set(user_id, "online"));
  };

  return {
    getInitialStatus: () => ({ ...statuses }),
    subscribe(onUpdate) {
      listeners.add(onUpdate);
      if (listeners.size === 1) {
        unsubscribe = getRealtime()?.subscribe(PRESENCE_TOPIC, {
          onEvent: (event) => {
            if (event.type === "presence.snapshot") {
              applySnapshot(event.payload as unknown as PresenceSnapshotPayload);
            } else if (event.type === "presence.changed") {
              const { user_id, status } = event.payload as unknown as PresenceChangedPayload;
              set(user_id, status);
            }
          },
        }) ?? null;
      }
      return () => {
        listeners.delete(onUpdate);
        if (listeners.size === 0) {
          unsubscribe?.();
          unsubscribe = null;
        }
      };
    },
  };
}

export const presenceSource: PresenceSource = createWebSocketPresenceSource();
