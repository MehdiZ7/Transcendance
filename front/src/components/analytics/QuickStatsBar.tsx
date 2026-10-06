'use client';

import { useState, useEffect } from 'react';
import { Card } from '@/components/ui/Card';
import type {
  OnlineStudentsData,
  ListingsTodayData,
  PendingReportsData,
  TotalListingsValueData,
  AverageListingPriceData,
} from '@/types';
import { analyticsApi } from '@/lib/api/analytics';
import { useAnalyticsLive } from '@/context/AnalyticsLiveContext';

interface QuickStatsBarProps {
  className?: string;
}

export default function QuickStatsBar({ className = '' }: QuickStatsBarProps) {
  const { refreshTrigger } = useAnalyticsLive();
  const [onlineStudents, setOnlineStudents] = useState<OnlineStudentsData | null>(null);
  const [listingsToday, setListingsToday] = useState<ListingsTodayData | null>(null);
  const [pendingReports, setPendingReports] = useState<PendingReportsData | null>(null);
  const [totalValue, setTotalValue] = useState<TotalListingsValueData | null>(null);
  const [averagePrice, setAveragePrice] = useState<AverageListingPriceData | null>(null);
  const [isLoading, setIsLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);

  const executeFetch = () => {
    return Promise.all([
      analyticsApi.getOnlineStudents(),
      analyticsApi.getListingsToday(),
      analyticsApi.getPendingReports(),
      analyticsApi.getTotalListingsValue(),
      analyticsApi.getAverageListingPrice(),
    ]).then(([dataOnline, dataListings, dataReports, dataTotal, dataAvg]) => {
      return { dataOnline, dataListings, dataReports, dataTotal, dataAvg };
    });
  };

  const handleRetry = () => {
    setIsLoading(true);
    setError(null);
    executeFetch()
      .then(({ dataOnline, dataListings, dataReports, dataTotal, dataAvg }) => {
        setOnlineStudents(dataOnline);
        setListingsToday(dataListings);
        setPendingReports(dataReports);
        setTotalValue(dataTotal);
        setAveragePrice(dataAvg);
      })
      .catch((err) => {
        setError(err instanceof Error ? err.message : 'Erreur lors du chargement des statistiques');
      })
      .finally(() => {
        setIsLoading(false);
      });
  };

  useEffect(() => {
    let ignore = false;
    const isRefresh = refreshTrigger > 0;

    executeFetch()
      .then(({ dataOnline, dataListings, dataReports, dataTotal, dataAvg }) => {
        if (!ignore) {
          setOnlineStudents(dataOnline);
          setListingsToday(dataListings);
          setPendingReports(dataReports);
          setTotalValue(dataTotal);
          setAveragePrice(dataAvg);
          setIsLoading(false);
        }
      })
      .catch((err) => {
        if (!ignore && !isRefresh) {
          setError(err instanceof Error ? err.message : 'Erreur lors du chargement des statistiques');
          setIsLoading(false);
        }
      });

    return () => {
      ignore = true;
    };
  }, [refreshTrigger]);

  const formatCurrency = (amount: number, currency = '€') => {
    const symbol = currency === 'EUR' ? '€' : currency;
    return `${Math.round(amount).toLocaleString('fr-FR')} ${symbol}`;
  };

  if (isLoading) {
    return (
      <div className={`grid grid-cols-1 sm:grid-cols-2 md:grid-cols-3 lg:grid-cols-5 gap-4 ${className}`}>
        {[...Array(5)].map((_, i) => (
          <Card key={i} className="animate-pulse flex flex-col justify-between min-h-[128px]">
            <div className="flex items-center justify-between mb-3">
              <div className="h-4 w-24 bg-slate-200 rounded"></div>
              <div className="h-8 w-8 bg-slate-200 rounded-lg"></div>
            </div>
            <div className="space-y-2">
              <div className="h-7 w-20 bg-slate-200 rounded"></div>
              <div className="h-3 w-28 bg-slate-100 rounded"></div>
            </div>
          </Card>
        ))}
      </div>
    );
  }

  if (error) {
    return (
      <div className="rounded-2xl border border-red-200 bg-red-50 p-4 text-sm text-red-700 flex items-center justify-between">
        <div>
          <p className="font-semibold">Erreur lors de la récupération des métriques</p>
          <p className="text-xs text-red-600 mt-0.5">{error}</p>
        </div>
        <button
          onClick={handleRetry}
          className="rounded-lg bg-red-600 px-3 py-1.5 text-xs font-medium text-white hover:bg-red-700 transition"
        >
          Réessayer
        </button>
      </div>
    );
  }

  return (
    <div className={`grid grid-cols-1 sm:grid-cols-2 md:grid-cols-3 lg:grid-cols-5 print:grid-cols-5 print:gap-2 gap-4 ${className}`}>
      {/* 1. Online students */}
      <Card className="flex flex-col justify-between border-green-200 hover:border-green-400 transition shadow-sm">
        <div className="flex items-center justify-between">
          <span className="text-xs font-semibold text-slate-500 uppercase tracking-wider">
            En ligne
          </span>
        </div>
        <div className="mt-4">
          <div className="text-2xl font-bold text-slate-900">
            {onlineStudents?.total ?? '-'}
          </div>
          <div className="mt-1 text-xs text-slate-400">
            Pic : <span className="font-medium text-slate-600">{onlineStudents?.peakToday ?? '-'}</span> studs
          </div>
        </div>
      </Card>

      {/* 2. Listings posted today */}
      <Card
        className={`flex flex-col justify-between transition shadow-sm ${
          listingsToday
            ? listingsToday.comparedToYesterdayPercent >= 0
              ? 'border-green-200 hover:border-green-400'
              : 'border-red-200 hover:border-red-400'
            : 'hover:border-slate-300'
        }`}
      >
        <div className="flex items-center justify-between">
          <span className="text-xs font-semibold text-slate-500 uppercase tracking-wider">
            Annonces du jour
          </span>
        </div>
        <div className="mt-4">
          <div className="text-2xl font-bold text-slate-900">
            {listingsToday?.count ?? '-'}
          </div>
          {listingsToday && (
            <div className="mt-1 text-xs text-slate-400">
              vs hier{' '}
              <span
                className={`font-medium ${
                  listingsToday.comparedToYesterdayPercent >= 0
                    ? 'text-green-600'
                    : 'text-red-600'
                }`}
              >
                {listingsToday.comparedToYesterdayPercent >= 0 ? '+' : ''}
                {listingsToday.comparedToYesterdayPercent}%
              </span>
            </div>
          )}
        </div>
      </Card>

      {/* 3. Pending reports */}
      <Card
        className={`flex flex-col justify-between transition shadow-sm ${
          (pendingReports?.count ?? 0) < 10
            ? 'border-orange-200 hover:border-orange-400'
            : 'border-red-200 hover:border-red-400'
        }`}
      >
        <div className="flex items-center justify-between">
          <span className="text-xs font-semibold text-slate-500 uppercase tracking-wider">
            Signalements
          </span>
        </div>
        <div className="mt-4">
          <div className="text-2xl font-bold text-slate-900">
            {pendingReports?.count ?? 0}
          </div>
          <div className="mt-1 text-xs text-slate-400">
            en attente de modération
          </div>
        </div>
      </Card>

      {/* 4. Total listings value */}
      <Card className="flex flex-col justify-between border-blue-200 hover:border-blue-400 transition shadow-sm">
        <div className="flex items-center justify-between">
          <span className="text-xs font-semibold text-slate-500 uppercase tracking-wider">
            Valeur totale
          </span>
        </div>
        <div className="mt-4">
          <div className="text-2xl font-bold text-slate-900">
            {totalValue ? formatCurrency(totalValue.totalValue, totalValue.currency) : '-'}
          </div>
          <div className="mt-1 text-xs text-slate-400">
            Actives :{' '}
            <span className="font-medium text-slate-600">
              {totalValue ? formatCurrency(totalValue.activeValue, totalValue.currency) : '-'}
            </span>
          </div>
        </div>
      </Card>

      {/* 5. Average price per listing */}
      <Card className="flex flex-col justify-between border-blue-200 hover:border-blue-400 transition shadow-sm">
        <div className="flex items-center justify-between">
          <span className="text-xs font-semibold text-slate-500 uppercase tracking-wider">
            Prix moyen
          </span>
        </div>
        <div className="mt-4">
          <div className="text-2xl font-bold text-slate-900">
            {averagePrice ? formatCurrency(averagePrice.averagePrice, averagePrice.currency) : '-'}
          </div>
          <div className="mt-1 text-xs text-slate-400">
            Médiane :{' '}
            <span className="font-medium text-slate-600">
              {averagePrice ? formatCurrency(averagePrice.medianPrice, averagePrice.currency) : '-'}
            </span>
          </div>
        </div>
      </Card>
    </div>
  );
}
