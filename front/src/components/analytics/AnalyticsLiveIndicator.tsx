'use client';

import { useAnalyticsLive } from '@/context/AnalyticsLiveContext';

export interface AnalyticsLiveIndicatorProps {
  className?: string;
}

export function AnalyticsLiveIndicator({ className = '' }: AnalyticsLiveIndicatorProps) {
  const { status, lastUpdated, refresh } = useAnalyticsLive();

  const formattedTime = lastUpdated
    ? lastUpdated.toLocaleTimeString('fr-FR', {
        hour: '2-digit',
        minute: '2-digit',
        second: '2-digit',
      })
    : null;

  return (
    <div
      className={`inline-flex items-center gap-2 px-3 py-1.5 rounded-xl border text-xs sm:text-sm font-medium transition-colors ${
        status === 'live'
          ? 'bg-emerald-50/80 border-emerald-200 text-emerald-800'
          : status === 'reconnecting'
          ? 'bg-amber-50/80 border-amber-200 text-amber-800'
          : status === 'closed'
          ? 'bg-rose-50/80 border-rose-200 text-rose-800'
          : 'bg-slate-50 border-slate-200 text-slate-600'
      } ${className}`}
    >
      {/* Status dot */}
      <span className="relative flex h-2 w-2 shrink-0">
        {status === 'live' && (
          <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-emerald-400 opacity-75" />
        )}
        {status === 'reconnecting' && (
          <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-amber-400 opacity-75" />
        )}
        <span
          className={`relative inline-flex rounded-full h-2 w-2 ${
            status === 'live'
              ? 'bg-emerald-500'
              : status === 'reconnecting'
              ? 'bg-amber-500'
              : status === 'closed'
              ? 'bg-rose-500'
              : 'bg-slate-400'
          }`}
        />
      </span>

      {/* Label depending on the status */}
      {status === 'connecting' && <span>Connexion…</span>}

      {status === 'reconnecting' && <span>Reconnexion…</span>}

      {status === 'closed' && (
        <span className="inline-flex items-center gap-1">
          <span>Hors ligne —</span>
          <button
            type="button"
            onClick={() => window.location.reload()}
            className="underline hover:text-rose-950 font-semibold cursor-pointer"
          >
            recharger la page
          </button>
        </span>
      )}

      {status === 'live' && (
        <div className="flex items-center gap-2">
          <span>En direct</span>
          {formattedTime && (
            <span className="text-emerald-700/80 text-xs hidden sm:inline">
              ({formattedTime})
            </span>
          )}
          <button
            type="button"
            onClick={refresh}
            title="Actualiser les données"
            aria-label="Actualiser les données"
            className="ml-1 inline-flex items-center gap-1 px-1.5 py-0.5 rounded-md hover:bg-emerald-100 text-emerald-800 transition-colors cursor-pointer text-xs font-semibold"
          >
            <svg
              className="w-3.5 h-3.5"
              fill="none"
              viewBox="0 0 24 24"
              stroke="currentColor"
              strokeWidth={2}
            >
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15"
              />
            </svg>
            <span className="hidden md:inline">Actualiser</span>
          </button>
        </div>
      )}
    </div>
  );
}

export default AnalyticsLiveIndicator;
