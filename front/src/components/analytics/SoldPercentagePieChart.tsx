'use client';

import { useState, useEffect, useMemo } from 'react';
import { ResponsiveContainer, PieChart, Pie, Cell, Tooltip } from 'recharts';
import { Card } from '@/components/ui/Card';
import type { SoldListingsData } from '@/types';
import { analyticsApi } from '@/lib/api/analytics';
import { useAnalyticsLive } from '@/context/AnalyticsLiveContext';

interface SoldChartSlice {
  name: string;
  count: number;
  percentage: number;
  color: string;
}

interface TooltipPayload {
  name?: string;
  value?: number;
  payload?: SoldChartSlice;
}

const CustomTooltip = ({
  active,
  payload,
}: {
  active?: boolean;
  payload?: TooltipPayload[];
}) => {
  if (!active || !payload || !payload.length || !payload[0].payload) return null;
  const item = payload[0].payload;

  return (
    <div className="relative z-50 rounded-xl border border-slate-200 bg-white/95 px-3.5 py-2.5 shadow-lg backdrop-blur-sm">
      <div className="flex items-center gap-2">
        <span
          className="h-3 w-3 rounded-full shrink-0 ring-2 ring-white"
          style={{ backgroundColor: item.color }}
        />
        <span className="text-sm font-semibold text-slate-900">
          {item.name}
        </span>
      </div>
      <div className="mt-1.5 flex items-baseline gap-2 text-xs text-slate-500">
        <span className="text-base font-bold text-slate-900">
          {item.percentage}%
        </span>
        <span>
          ({item.count} annonce{item.count > 1 ? 's' : ''})
        </span>
      </div>
    </div>
  );
};

export interface SoldPercentagePieChartProps {
  asCard?: boolean;
  className?: string;
}

export default function SoldPercentagePieChart({
  asCard = false,
  className = '',
}: SoldPercentagePieChartProps = {}) {
  const { refreshTrigger } = useAnalyticsLive();
  const [data, setData] = useState<SoldListingsData | null>(null);
  const [isLoading, setIsLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);

  const handleRetry = () => {
    setIsLoading(true);
    setError(null);
    analyticsApi.getSoldPercentage()
      .then((resData) => {
        setData(resData);
      })
      .catch((err) => {
        setError(err instanceof Error ? err.message : 'Erreur lors du chargement des données');
      })
      .finally(() => {
        setIsLoading(false);
      });
  };

  useEffect(() => {
    let ignore = false;
    // Background refresh: keep the current view instead of the skeleton if the request fails.
    const isRefresh = refreshTrigger > 0;

    analyticsApi.getSoldPercentage()
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

  const chartData = useMemo<SoldChartSlice[]>(() => {
    if (!data) return [];
    const soldCount = data.soldCount;
    const activeCount = data.activeCount;
    const total = data.totalCount || soldCount + activeCount;
    const soldPct = data.percentage ?? (total > 0 ? Math.round((soldCount / total) * 1000) / 10 : 0);
    const activePct = Math.max(0, Math.round((100 - soldPct) * 10) / 10);

    const slices: SoldChartSlice[] = [
      {
        name: 'Vendues',
        count: soldCount,
        percentage: soldPct,
        color: '#00babc',
      },
      {
        name: 'En ligne',
        count: activeCount,
        percentage: activePct,
        color: '#3b82f6',
      },
    ];

    const activeSlices = slices.filter((s) => s.count > 0);
    return activeSlices.length > 0 ? activeSlices : slices;
  }, [data]);

  const activePercentage = useMemo(() => {
    if (!data) return 0;
    return Math.max(0, Math.round((100 - data.percentage) * 10) / 10);
  }, [data]);

  const content = (
    <div className="w-full">
      {/* Header with title and subtitle */}
      <div>
        <h2 className="text-lg font-semibold text-slate-900">
          Taux d&apos;annonces vendues
        </h2>
        <p className="text-sm text-slate-500">
          Proportion d&apos;annonces vendues par rapport aux annonces actives
        </p>
      </div>

      {isLoading && (
        <div className="mt-8 flex flex-col items-center justify-center gap-3 py-16">
          <div className="h-8 w-8 animate-spin rounded-full border-4 border-[#00babc] border-t-transparent"></div>
          <span className="text-sm text-slate-500">
            Chargement du graphique...
          </span>
        </div>
      )}

      {error && (
        <div className="mt-6 rounded-xl border border-red-200 bg-red-50 p-4 text-sm text-red-700">
          <p className="font-medium">Impossible de charger les données</p>
          <p className="mt-1 text-xs">{error}</p>
          <button
            onClick={handleRetry}
            className="mt-3 inline-flex items-center rounded-lg bg-red-600 px-3 py-1.5 text-xs font-semibold text-white transition hover:bg-red-700"
          >
            Réessayer
          </button>
        </div>
      )}

      {!isLoading && !error && data && (
        <div className="mt-6">
          {/* Graphique Recharts Pie / Donut */}
          <div className="relative flex justify-center h-72 w-full">
            <ResponsiveContainer width="100%" height="100%" className="relative z-10">
              <PieChart>
                <Pie
                  data={chartData}
                  dataKey="percentage"
                  nameKey="name"
                  cx="50%"
                  cy="50%"
                  outerRadius={105}
                  innerRadius={62}
                  paddingAngle={3}
                  isAnimationActive={true}
                  animationDuration={750}
                  stroke="#ffffff"
                  strokeWidth={2}
                >
                  {chartData.map((entry) => (
                    <Cell
                      key={`cell-${entry.name}`}
                      fill={entry.color}
                    />
                  ))}
                </Pie>
                {/* Donut info center (inside the SVG for perfect centering on screen and PDF) */}
                <text
                  x="50%"
                  y="46%"
                  textAnchor="middle"
                  dominantBaseline="central"
                  style={{ fontSize: '28px', fontWeight: 700, fill: '#0f172a' }}
                >
                  {data.percentage}%
                </text>
                <text
                  x="50%"
                  y="57%"
                  textAnchor="middle"
                  dominantBaseline="central"
                  style={{ fontSize: '11px', fontWeight: 500, fill: '#94a3b8', letterSpacing: '0.05em' }}
                >
                  VENDUES
                </text>
                <Tooltip content={<CustomTooltip />} wrapperStyle={{ zIndex: 50 }} />
              </PieChart>
            </ResponsiveContainer>
          </div>

          {/* Numeric details grid */}
          <div className="grid grid-cols-4 gap-2 pt-4 sm:grid-cols-4">
            <div className="rounded-xl bg-slate-50 p-2.5 text-center transition hover:bg-slate-100/80">
              <div className="flex items-center justify-center gap-1.5 truncate text-xs font-medium text-slate-600">
                <span
                  className="h-2 w-2 rounded-full shrink-0"
                  style={{ backgroundColor: '#00babc' }}
                />
                <span className="truncate">Vendues</span>
              </div>
              <div className="mt-1 text-base font-bold text-slate-900">
                {data.percentage}%
              </div>
              <div className="text-[11px] text-slate-400">
                {data.soldCount} annonce{data.soldCount > 1 ? 's' : ''}
              </div>
            </div>

            <div className="rounded-xl bg-slate-50 p-2.5 text-center transition hover:bg-slate-100/80">
              <div className="flex items-center justify-center gap-1.5 truncate text-xs font-medium text-slate-600">
                <span
                  className="h-2 w-2 rounded-full shrink-0"
                  style={{ backgroundColor: '#3b82f6' }}
                />
                <span className="truncate">En ligne</span>
              </div>
              <div className="mt-1 text-base font-bold text-slate-900">
                {activePercentage}%
              </div>
              <div className="text-[11px] text-slate-400">
                {data.activeCount} annonce{data.activeCount > 1 ? 's' : ''}
              </div>
            </div>

            <div className="rounded-xl bg-slate-50 p-2.5 text-center transition hover:bg-slate-100/80">
              <div className="flex items-center justify-center gap-1.5 truncate text-xs font-medium text-slate-600">
                <span
                  className="h-2 w-2 rounded-full shrink-0"
                  style={{ backgroundColor: '#64748b' }}
                />
                <span className="truncate">Total</span>
              </div>
              <div className="mt-1 text-base font-bold text-slate-900">
                {data.totalCount}
              </div>
              <div className="text-[11px] text-slate-400">
                annonces créées
              </div>
            </div>

            <div className="rounded-xl bg-slate-50 p-2.5 text-center transition hover:bg-slate-100/80">
              <div className="flex items-center justify-center gap-1.5 truncate text-xs font-medium text-slate-600">
                <span
                  className="h-2 w-2 rounded-full shrink-0"
                  style={{ backgroundColor: '#f59e0b' }}
                />
                <span className="truncate">Délai moyen</span>
              </div>
              <div className="mt-1 text-base font-bold text-slate-900">
                {data.averageTimeToSellDays} j
              </div>
              <div className="text-[11px] text-slate-400">
                temps de vente
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );

  if (asCard) {
    return <Card className={className}>{content}</Card>;
  }

  return <div className={className}>{content}</div>;
}
