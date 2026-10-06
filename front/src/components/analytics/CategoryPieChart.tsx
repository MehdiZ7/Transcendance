'use client';

import { useState, useEffect, useMemo } from 'react';
import { ResponsiveContainer, PieChart, Pie, Cell, Tooltip } from 'recharts';
import { Card } from '@/components/ui/Card';
import type { CategoryDistributionData, CategoryDistributionItem } from '@/types';
import { analyticsApi } from '@/lib/api/analytics';
import { useAnalyticsLive } from '@/context/AnalyticsLiveContext';

const FALLBACK_COLORS = ['#00babc', '#3b82f6', '#10b981', '#f59e0b', '#8b5cf6', '#ec4899'];

interface TooltipPayload {
  name?: string;
  value?: number;
  payload?: CategoryDistributionItem;
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
          style={{ backgroundColor: item.color || '#00babc' }}
        />
        <span className="text-sm font-semibold text-slate-900">
          {item.categoryName}
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

export interface CategoryPieChartProps {
  asCard?: boolean;
  className?: string;
}

export default function CategoryPieChart({
  asCard = false,
  className = '',
}: CategoryPieChartProps = {}) {
  const { refreshTrigger } = useAnalyticsLive();
  const [data, setData] = useState<CategoryDistributionData | null>(null);
  const [isLoading, setIsLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);

  const handleRetry = () => {
    setIsLoading(true);
    setError(null);
    analyticsApi.getCategoryDistribution()
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

    analyticsApi.getCategoryDistribution()
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

  // Only draw categories with at least one listing in the SVG, for a cleaner render
  const activeCategories = useMemo(() => {
    if (!data?.categories) return [];
    const filtered = data.categories.filter((c) => c.count > 0);
    return filtered.length > 0 ? filtered : data.categories;
  }, [data]);

  const content = (
    <div className="w-full">
      {/* Header with title and subtitle */}
      <div>
        <h2 className="text-lg font-semibold text-slate-900">
          Répartition par catégorie
        </h2>
        <p className="text-sm text-slate-500">
          Pourcentage et volume d&apos;annonces selon leur catégorie
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
          <p className="font-medium">Impossible de charger la répartition</p>
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
                  data={activeCategories}
                  dataKey="percentage"
                  nameKey="categoryName"
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
                  {activeCategories.map((entry, index) => (
                    <Cell
                      key={`cell-${entry.categoryId}`}
                      fill={entry.color || FALLBACK_COLORS[index % FALLBACK_COLORS.length]}
                    />
                  ))}
                </Pie>
                {/* Donut info center (inside the SVG for perfect centering on screen and PDF) */}
                <text
                  x="50%"
                  y="46%"
                  textAnchor="middle"
                  dominantBaseline="central"
                  style={{ fontSize: '24px', fontWeight: 700, fill: '#0f172a' }}
                >
                  {data.totalListings}
                </text>
                <text
                  x="50%"
                  y="57%"
                  textAnchor="middle"
                  dominantBaseline="central"
                  style={{ fontSize: '11px', fontWeight: 500, fill: '#94a3b8', letterSpacing: '0.05em' }}
                >
                  ANNONCES
                </text>
                <Tooltip content={<CustomTooltip />} wrapperStyle={{ zIndex: 50 }} />
              </PieChart>
            </ResponsiveContainer>
          </div>

          {/* Numeric details grid for each category */}
          <div className="grid grid-cols-2 gap-2 pt-4 sm:grid-cols-3 md:grid-cols-5">
            {data.categories.map((cat, idx) => {
              const color = cat.color || FALLBACK_COLORS[idx % FALLBACK_COLORS.length];
              return (
                <div
                  key={cat.categoryId}
                  className="rounded-xl bg-slate-50 p-2.5 text-center transition hover:bg-slate-100/80"
                >
                  <div className="flex items-center justify-center gap-1.5 truncate text-xs font-medium text-slate-600">
                    <span
                      className="h-2 w-2 rounded-full shrink-0"
                      style={{ backgroundColor: color }}
                    />
                    <span className="truncate">{cat.categoryName}</span>
                  </div>
                  <div className="mt-1 text-base font-bold text-slate-900">
                    {cat.percentage}%
                  </div>
                  <div className="text-[11px] text-slate-400">
                    {cat.count} annonce{cat.count > 1 ? 's' : ''}
                  </div>
                </div>
              );
            })}
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

