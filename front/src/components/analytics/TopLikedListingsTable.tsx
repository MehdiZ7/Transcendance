'use client';

import { useState, useEffect } from 'react';
import { Card } from '@/components/ui/Card';
import { ListingTableRow, ListingTableRowSkeleton } from '@/components/listings/ListingTableRow';
import type { TopLikedListingsData } from '@/types';
import { analyticsApi } from '@/lib/api/analytics';
import { useIsMounted } from '@/hooks/useIsMounted';
import { useAnalyticsLive } from '@/context/AnalyticsLiveContext';

export interface TopLikedListingsTableProps {
  asCard?: boolean;
  className?: string;
}

export default function TopLikedListingsTable({
  asCard = true,
  className = '',
}: TopLikedListingsTableProps) {
  const { refreshTrigger } = useAnalyticsLive();
  const [data, setData] = useState<TopLikedListingsData | null>(null);
  const [isLoading, setIsLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);
  const isMounted = useIsMounted();

  const fetchData = () => {
    setIsLoading(true);
    setError(null);
    analyticsApi.getTopLikedListings()
      .then((resData) => {
        setData(resData);
      })
      .catch((err) => {
        setError(err instanceof Error ? err.message : 'Erreur lors du chargement des annonces les plus likées');
      })
      .finally(() => {
        setIsLoading(false);
      });
  };

  useEffect(() => {
    let ignore = false;
    const isRefresh = refreshTrigger > 0;

    analyticsApi.getTopLikedListings()
      .then((resData) => {
        if (!ignore) {
          setData(resData);
          setIsLoading(false);
        }
      })
      .catch((err) => {
        if (!ignore && !isRefresh) {
          setError(err instanceof Error ? err.message : 'Erreur lors du chargement des données');
          setIsLoading(false);
        }
      });

    return () => {
      ignore = true;
    };
  }, [refreshTrigger]);

  const content = (
    <div className="space-y-4">
      {/* Section header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
        <div className="space-y-1">
          <div className="flex items-center gap-2">
            <div className="flex items-center justify-center h-8 w-8 rounded-lg bg-rose-50 text-rose-600 border border-rose-100">
              <svg className="w-4 h-4 fill-current" viewBox="0 0 24 24">
                <path d="M12 21.35l-1.45-1.32C5.4 15.36 2 12.28 2 8.5 2 5.42 4.42 3 7.5 3c1.74 0 3.41.81 4.5 2.09C13.09 3.81 14.76 3 16.5 3 19.58 3 22 5.42 22 8.5c0 3.78-3.4 6.86-8.55 11.54L12 21.35z" />
              </svg>
            </div>
            <h2 className="text-lg font-bold text-slate-900">
              Top annonces les plus likées
            </h2>
            <span className="inline-flex items-center px-2 py-0.5 rounded-full text-xs font-semibold bg-rose-100/80 text-rose-800">
              Top 5
            </span>
          </div>
        </div>

        <button
          type="button"
          onClick={fetchData}
          disabled={isMounted ? isLoading : false}
          suppressHydrationWarning
          className="self-start sm:self-auto inline-flex items-center gap-1.5 px-3 py-1.5 text-xs font-semibold text-slate-600 hover:text-slate-900 bg-slate-50 hover:bg-slate-100 border border-slate-200 rounded-lg transition-colors cursor-pointer disabled:opacity-50"
          title="Actualiser les données"
        >
          <svg
            className={`w-3.5 h-3.5 ${isLoading ? 'animate-spin' : ''}`}
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
          <span>Actualiser</span>
        </button>
      </div>

      {/* Error state */}
      {error && (
        <div className="rounded-xl border border-rose-200 bg-rose-50 p-4 text-center">
          <p className="text-sm font-medium text-rose-700">{error}</p>
          <button
            type="button"
            onClick={fetchData}
            className="mt-2 text-xs font-semibold text-rose-800 underline hover:no-underline cursor-pointer"
          >
            Réessayer
          </button>
        </div>
      )}

      {/* Tableau responsive */}
      <div className="overflow-x-auto -mx-6 px-6 sm:mx-0 sm:px-0">
        <table className="w-full text-left border-collapse min-w-[640px]">
          <thead>
            <tr className="border-b border-slate-200 text-xs font-semibold text-slate-500 uppercase tracking-wider bg-slate-50/50">
              <th scope="col" className="py-3 pl-4 pr-3 sm:pl-6 text-center w-16">
                Rang
              </th>
              <th scope="col" className="py-3 px-3">
                Annonce
              </th>
              <th scope="col" className="py-3 px-3 hidden md:table-cell w-32">
                Catégorie
              </th>
              <th scope="col" className="py-3 px-3 w-24">
                Prix
              </th>
              <th scope="col" className="py-3 px-3 hidden sm:table-cell text-center w-24">
                Vues
              </th>
              <th scope="col" className="py-3 px-3 text-center w-28">
                Favoris
              </th>
              <th scope="col" className="py-3 pl-3 pr-4 sm:pr-6 text-right w-24">
                Action
              </th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-100">
            {isLoading && (
              <>
                <ListingTableRowSkeleton />
                <ListingTableRowSkeleton />
                <ListingTableRowSkeleton />
                <ListingTableRowSkeleton />
                <ListingTableRowSkeleton />
              </>
            )}

            {!isLoading && !error && data?.listings && data.listings.length > 0 && (
              data.listings.map((item, idx) => (
                <ListingTableRow
                  key={item.id || item.public_id || idx}
                  listing={item}
                  rank={item.rank || idx + 1}
                />
              ))
            )}

            {!isLoading && !error && (!data?.listings || data.listings.length === 0) && (
              <tr>
                <td colSpan={7} className="py-12 text-center text-sm text-slate-500">
                  <div className="flex flex-col items-center justify-center gap-2">
                    <svg
                      className="w-8 h-8 text-slate-300"
                      fill="none"
                      viewBox="0 0 24 24"
                      stroke="currentColor"
                      strokeWidth={1.5}
                    >
                      <path
                        strokeLinecap="round"
                        strokeLinejoin="round"
                        d="M20 13V6a2 2 0 00-2-2H6a2 2 0 00-2 2v7m16 0v5a2 2 0 01-2 2H6a2 2 0 01-2-2v-5m16 0h-2.586a1 1 0 00-.707.293l-2.414 2.414a1 1 0 01-.707.293h-3.172a1 1 0 01-.707-.293l-2.414-2.414A1 1 0 006.586 13H4"
                      />
                    </svg>
                    <span>Aucune annonce disponible dans le classement</span>
                  </div>
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  );

  if (asCard) {
    return <Card className={className}>{content}</Card>;
  }

  return <div className={className}>{content}</div>;
}
