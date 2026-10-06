'use client';

import { createContext, useCallback, useContext, useEffect, useRef, useState } from 'react';
import { getApiBaseUrl } from '@/lib/api/client';

// 'closed' = the browser GAVE UP (401/403/502): EventSource will not retry.
// Distinct from 'reconnecting', otherwise the indicator would lie forever.
type LiveStatus = 'connecting' | 'live' | 'reconnecting' | 'closed';

interface AnalyticsLive {
  status: LiveStatus;
  lastUpdated: Date | null;
  refreshTrigger: number;
  refresh: () => void;
}

const DEBOUNCE_MS = 500;
const PRESENCE_POLL_MS = 60_000; // see "Known limitations"

const AnalyticsLiveContext = createContext<AnalyticsLive | null>(null);

export function AnalyticsLiveProvider({ children }: { children: React.ReactNode }) {
  const [status, setStatus] = useState<LiveStatus>('connecting');
  const [lastUpdated, setLastUpdated] = useState<Date | null>(null);
  const [refreshTrigger, setRefreshTrigger] = useState(0);
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);

  const refresh = useCallback(() => {
    setRefreshTrigger((n) => n + 1);
    setLastUpdated(new Date());
  }, []);

  useEffect(() => {
    if (typeof window === 'undefined') return; // no stream during SSR

    const source = new EventSource(`${getApiBaseUrl()}/analytics/stream`);

    // Without Last-Event-ID, invalidations emitted during a drop are lost:
    // refetching on every (re)connection closes the gap.
    source.addEventListener('connected', () => {
      setStatus('live');
      refresh();
    });

    source.addEventListener('analytics_update', () => {
      if (timer.current) clearTimeout(timer.current);
      timer.current = setTimeout(refresh, DEBOUNCE_MS);
    });

    source.onerror = () => {
      setStatus(source.readyState === EventSource.CLOSED ? 'closed' : 'reconnecting');
    };

    // Presence, daily peak, midnight switch: no business event drives them.
    // See "Known limitations".
    const poll = setInterval(refresh, PRESENCE_POLL_MS);

    return () => {
      clearInterval(poll);
      if (timer.current) clearTimeout(timer.current);
      source.close();
    };
  }, [refresh]);

  return (
    <AnalyticsLiveContext.Provider value={{ status, lastUpdated, refreshTrigger, refresh }}>
      {children}
    </AnalyticsLiveContext.Provider>
  );
}

// refreshTrigger stays 0 until a refresh has happened: components use it to
// skip the fetch on mount.
export function useAnalyticsLive(): AnalyticsLive {
  const value = useContext(AnalyticsLiveContext);
  if (value === null) {
    throw new Error('useAnalyticsLive must be used inside <AnalyticsLiveProvider>');
  }
  return value;
}
