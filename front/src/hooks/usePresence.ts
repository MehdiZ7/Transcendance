"use client";

import { useEffect, useState } from "react";
import { presenceSource } from "@/lib/api/presence";
import type { PresenceStatus } from "@/types";

// Hook for tracking user online/offline status via WebSocket

export function usePresence() {
  const [statuses, setStatuses] = useState<Record<string, PresenceStatus>>(
    presenceSource.getInitialStatus
  );

  useEffect(() => {
    return presenceSource.subscribe((update) => {
      setStatuses((prev) => ({ ...prev, [update.user_id]: update.status }));
    });
  }, []);

  const isOnline = (userId: string) => statuses[userId] === "online";

  return { statuses, isOnline };
}
