'use client';

import { useState, useEffect, useMemo, useRef } from 'react';
import {
  ResponsiveContainer,
  AreaChart,
  Area,
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
} from 'recharts';
import { Card } from '@/components/ui/Card';
import type { ListingsBetweenDatesData, DailyListingCount } from '@/types';
import { analyticsApi } from '@/lib/api/analytics';
import { useAnalyticsLive } from '@/context/AnalyticsLiveContext';
import { MAX_ANALYTICS_DATE, MAX_ANALYTICS_RANGE_DAYS, MIN_ANALYTICS_DATE } from '@/lib/limits';

const toFrenchDate = (iso: string) => iso.split('-').reverse().join('/');

// The API's rules (422 otherwise), checked before asking it: an input's
// min/max does not stop a date typed by hand, and knows nothing of the range
function rangeError(start: string, end: string): string | null {
  for (const day of [start, end]) {
    if (day && (!/^\d{4}-\d{2}-\d{2}$/.test(day) || day < MIN_ANALYTICS_DATE || day > MAX_ANALYTICS_DATE)) {
      return `Choisissez des dates entre le ${toFrenchDate(MIN_ANALYTICS_DATE)} et le ${toFrenchDate(MAX_ANALYTICS_DATE)}.`;
    }
  }
  if (start && end && Math.abs(Date.parse(end) - Date.parse(start)) / 86_400_000 > MAX_ANALYTICS_RANGE_DAYS) {
    return `La période ne peut pas dépasser ${MAX_ANALYTICS_RANGE_DAYS} jours.`;
  }
  return null;
}

export interface ListingsBetweenDatesChartProps {
  asCard?: boolean;
  className?: string;
  defaultPreset?: '7d' | '14d' | '30d' | 'month';
}

type PresetType = '7d' | '14d' | '30d' | 'month' | 'custom';
type ChartType = 'area' | 'bar';

interface TooltipPayloadItem {
  name?: string;
  value?: number;
  payload?: DailyListingCount;
}

// Format a JS date as an ISO YYYY-MM-DD string
function toDateInputValue(d: Date): string {
  const year = d.getFullYear();
  const month = String(d.getMonth() + 1).padStart(2, '0');
  const day = String(d.getDate()).padStart(2, '0');
  return `${year}-${month}-${day}`;
}

// Format a YYYY-MM-DD date for the X axis (e.g. 8 Sep)
function formatXAxisDate(dateStr: string): string {
  if (!dateStr) return '';
  const [y, m, d] = dateStr.split('-');
  if (!y || !m || !d) return dateStr;
  const dateObj = new Date(parseInt(y, 10), parseInt(m, 10) - 1, parseInt(d, 10));
  return dateObj.toLocaleDateString('fr-FR', { day: 'numeric', month: 'short' });
}

// Format a full YYYY-MM-DD date for the tooltip (e.g. Tuesday 8 September 2026)
function formatTooltipDate(dateStr: string): string {
  if (!dateStr) return '';
  const [y, m, d] = dateStr.split('-');
  if (!y || !m || !d) return dateStr;
  const dateObj = new Date(parseInt(y, 10), parseInt(m, 10) - 1, parseInt(d, 10));
  return dateObj.toLocaleDateString('fr-FR', {
    weekday: 'long',
    day: 'numeric',
    month: 'long',
    year: 'numeric',
  });
}

// Custom tooltip for Recharts
const CustomTooltip = ({
  active,
  payload,
}: {
  active?: boolean;
  payload?: TooltipPayloadItem[];
}) => {
  if (!active || !payload || !payload.length || !payload[0].payload) return null;
  const item = payload[0].payload;
  const count = item.count;

  return (
    <div className="relative z-50 rounded-xl border border-slate-200 bg-white/95 px-3.5 py-2.5 shadow-lg backdrop-blur-sm">
      <p className="text-xs font-medium text-slate-500 capitalize">
        {formatTooltipDate(item.date)}
      </p>
      <div className="mt-1.5 flex items-center gap-2">
        <span className="h-2.5 w-2.5 rounded-full bg-[#00babc] ring-2 ring-[#00babc]/25" />
        <span className="text-sm font-bold text-slate-900">
          {count} <span className="text-xs font-normal text-slate-500">{count > 1 ? 'annonces publiées' : 'annonce publiée'}</span>
        </span>
      </div>
    </div>
  );
};

export function ListingsBetweenDatesChart({
  asCard = false,
  className = '',
  defaultPreset = '30d',
}: ListingsBetweenDatesChartProps) {
  // Initial date calculation based on the default preset
  const initialDates = useMemo(() => {
    const end = new Date();
    const start = new Date();
    if (defaultPreset === '7d') {
      start.setDate(end.getDate() - 6);
    } else if (defaultPreset === '14d') {
      start.setDate(end.getDate() - 13);
    } else if (defaultPreset === 'month') {
      start.setDate(1);
    } else {
      start.setDate(end.getDate() - 29);
    }
    return {
      start: toDateInputValue(start),
      end: toDateInputValue(end),
    };
  }, [defaultPreset]);

  const { refreshTrigger } = useAnalyticsLive();
  const [startDate, setStartDate] = useState<string>(initialDates.start);
  const [endDate, setEndDate] = useState<string>(initialDates.end);
  const [activePreset, setActivePreset] = useState<PresetType>(defaultPreset);
  const [chartType, setChartType] = useState<ChartType>('area');

  const [data, setData] = useState<ListingsBetweenDatesData | null>(null);
  const [isLoading, setIsLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);

  const invalidRange = useMemo(() => rangeError(startDate, endDate), [startDate, endDate]);

  const prevDatesRef = useRef({ startDate, endDate });
  const isFirstMountRef = useRef(true);

  // Fetch data for the selected range
  useEffect(() => {
    let ignore = false;
    const isFirstMount = isFirstMountRef.current;
    isFirstMountRef.current = false;

    const datesChanged =
      prevDatesRef.current.startDate !== startDate ||
      prevDatesRef.current.endDate !== endDate;
    prevDatesRef.current = { startDate, endDate };

    // A silent background refresh only applies if the dates did not change
    // and it is not the component's first mount.
    const isSilentRefresh = !isFirstMount && !datesChanged;

    // nothing to ask the API: the range message replaces the chart
    if (invalidRange) return;

    if (!isSilentRefresh) {
      setIsLoading(true);
      setError(null);
    }

    analyticsApi.getListingsBetweenDates(startDate, endDate)
      .then((resData) => {
        if (!ignore) {
          setData(resData);
          setError(null);
          setIsLoading(false);
        }
      })
      .catch((err) => {
        if (!ignore) {
          if (!isSilentRefresh) {
            setError(err instanceof Error ? err.message : 'Erreur lors du chargement des publications');
            setIsLoading(false);
          }
        }
      });

    return () => {
      ignore = true;
    };
  }, [startDate, endDate, refreshTrigger, invalidRange]);

  const handleRetry = () => {
    if (invalidRange) return;
    setIsLoading(true);
    setError(null);

    analyticsApi.getListingsBetweenDates(startDate, endDate)
      .then((resData) => {
        setData(resData);
        setError(null);
      })
      .catch((err) => {
        setError(err instanceof Error ? err.message : 'Erreur lors du chargement des publications');
      })
      .finally(() => {
        setIsLoading(false);
      });
  };

  // Handle the time range shortcut buttons
  const applyPreset = (preset: '7d' | '14d' | '30d' | 'month') => {
    setIsLoading(true);
    setError(null);
    const end = new Date();
    const start = new Date();

    if (preset === '7d') {
      start.setDate(end.getDate() - 6);
    } else if (preset === '14d') {
      start.setDate(end.getDate() - 13);
    } else if (preset === 'month') {
      start.setDate(1);
    } else {
      start.setDate(end.getDate() - 29);
    }

    const sStr = toDateInputValue(start);
    const eStr = toDateInputValue(end);

    setActivePreset(preset);
    setStartDate(sStr);
    setEndDate(eStr);
  };

  const handleStartDateChange = (val: string) => {
    setIsLoading(true);
    setError(null);
    setActivePreset('custom');
    setStartDate(val);
    if (val && endDate && val > endDate) {
      setEndDate(val);
    }
  };

  const handleEndDateChange = (val: string) => {
    setIsLoading(true);
    setError(null);
    setActivePreset('custom');
    setEndDate(val);
    if (val && startDate && val < startDate) {
      setStartDate(val);
    }
  };

  // Derived statistics
  const stats = useMemo(() => {
    if (!data?.dailyBreakdown || data.dailyBreakdown.length === 0) {
      return {
        total: 0,
        average: '0',
        peakCount: 0,
        peakDate: null as string | null,
      };
    }

    const total = data.totalCount ?? data.dailyBreakdown.reduce((acc, curr) => acc + curr.count, 0);
    const daysCount = data.dailyBreakdown.length;
    const average = daysCount > 0 ? (total / daysCount).toFixed(1) : '0';

    let peak = data.dailyBreakdown[0];
    for (let i = 1; i < data.dailyBreakdown.length; i++) {
      if (data.dailyBreakdown[i].count > peak.count) {
        peak = data.dailyBreakdown[i];
      }
    }

    return {
      total,
      average,
      peakCount: peak.count,
      peakDate: peak.date,
    };
  }, [data]);

  const content = (
    <div className="w-full space-y-6">
      {/* Header: title & date selectors */}
      <div className="flex flex-col gap-4 lg:flex-row lg:items-center lg:justify-between">
        <div>
          <h2 className="text-lg font-semibold text-slate-900">
            Annonces publiées sur la période
          </h2>
          <p className="text-sm text-slate-500">
            Évolution quotidienne des créations d&apos;annonces selon l&apos;intervalle sélectionné
          </p>
        </div>

        {/* Date controls and chart types */}
        <div className="flex flex-wrap items-center gap-2 sm:gap-3">
          {/* Time range shortcut buttons */}
          <div className="inline-flex rounded-lg bg-slate-100 p-1">
            <button
              type="button"
              onClick={() => applyPreset('7d')}
              className={`rounded-md px-2.5 py-1 text-xs font-medium transition-all ${
                activePreset === '7d'
                  ? 'bg-white text-slate-900 shadow-xs'
                  : 'text-slate-600 hover:text-slate-900'
              }`}
            >
              7j
            </button>
            <button
              type="button"
              onClick={() => applyPreset('14d')}
              className={`rounded-md px-2.5 py-1 text-xs font-medium transition-all ${
                activePreset === '14d'
                  ? 'bg-white text-slate-900 shadow-xs'
                  : 'text-slate-600 hover:text-slate-900'
              }`}
            >
              14j
            </button>
            <button
              type="button"
              onClick={() => applyPreset('30d')}
              className={`rounded-md px-2.5 py-1 text-xs font-medium transition-all ${
                activePreset === '30d'
                  ? 'bg-white text-slate-900 shadow-xs'
                  : 'text-slate-600 hover:text-slate-900'
              }`}
            >
              30j
            </button>
            <button
              type="button"
              onClick={() => applyPreset('month')}
              className={`rounded-md px-2.5 py-1 text-xs font-medium transition-all ${
                activePreset === 'month'
                  ? 'bg-white text-slate-900 shadow-xs'
                  : 'text-slate-600 hover:text-slate-900'
              }`}
            >
              Ce mois
            </button>
          </div>

          {/* Custom date selectors */}
          <div className="flex items-center gap-1.5 text-xs text-slate-500">
            <span className="hidden sm:inline">Du</span>
            <input
              type="date"
              aria-label="Date de début"
              min={MIN_ANALYTICS_DATE}
              max={MAX_ANALYTICS_DATE}
              value={startDate}
              onChange={(e) => handleStartDateChange(e.target.value)}
              className="rounded-lg border border-slate-200 bg-white px-2.5 py-1 text-xs font-medium text-slate-700 shadow-2xs outline-none transition focus:border-[#00babc] focus:ring-1 focus:ring-[#00babc]"
            />
            <span>au</span>
            <input
              type="date"
              aria-label="Date de fin"
              min={MIN_ANALYTICS_DATE}
              max={MAX_ANALYTICS_DATE}
              value={endDate}
              onChange={(e) => handleEndDateChange(e.target.value)}
              className="rounded-lg border border-slate-200 bg-white px-2.5 py-1 text-xs font-medium text-slate-700 shadow-2xs outline-none transition focus:border-[#00babc] focus:ring-1 focus:ring-[#00babc]"
            />
          </div>

          {/* Toggle Type de Graphique (Courbe / Barres) */}
          <div className="inline-flex rounded-lg border border-slate-200 bg-white p-0.5 shadow-2xs">
            <button
              type="button"
              onClick={() => setChartType('area')}
              title="Affichage en courbe"
              aria-label="Affichage en courbe"
              className={`rounded px-2 py-1 text-xs font-medium transition ${
                chartType === 'area'
                  ? 'bg-[#00babc]/10 text-[#009698] font-semibold'
                  : 'text-slate-500 hover:text-slate-900'
              }`}
            >
              Courbe
            </button>
            <button
              type="button"
              onClick={() => setChartType('bar')}
              title="Affichage en barres"
              aria-label="Affichage en barres"
              className={`rounded px-2 py-1 text-xs font-medium transition ${
                chartType === 'bar'
                  ? 'bg-[#00babc]/10 text-[#009698] font-semibold'
                  : 'text-slate-500 hover:text-slate-900'
              }`}
            >
              Barres
            </button>
          </div>
        </div>
      </div>

      {/* Summary KPI badges */}
      <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
        <div className="rounded-xl border border-slate-100 bg-slate-50/70 p-3">
          <p className="text-xs font-medium text-slate-500">Total publié</p>
          <div className="mt-1 flex items-baseline gap-2">
            <span className="text-xl font-bold text-slate-900">
              {error || invalidRange || (isLoading && !data) ? '-' : stats.total}
            </span>
            <span className="text-xs text-slate-400">annonces</span>
          </div>
        </div>

        <div className="rounded-xl border border-slate-100 bg-slate-50/70 p-3">
          <p className="text-xs font-medium text-slate-500">Moyenne quotidienne</p>
          <div className="mt-1 flex items-baseline gap-2">
            <span className="text-xl font-bold text-slate-900">
              {error || invalidRange || (isLoading && !data) ? '-' : stats.average}
            </span>
            <span className="text-xs text-slate-400">annonces / jour</span>
          </div>
        </div>

        <div className="rounded-xl border border-slate-100 bg-slate-50/70 p-3">
          <p className="text-xs font-medium text-slate-500">Pic d&apos;activité</p>
          <div className="mt-1 flex items-baseline gap-2">
            <span className="text-xl font-bold text-[#009698]">
              {error || invalidRange || (isLoading && !data) ? '-' : `${stats.peakCount}`}
            </span>
            <span className="text-xs text-slate-500">
              {!error && !invalidRange && stats.peakDate ? `le ${formatXAxisDate(stats.peakDate)}` : 'annonces max'}
            </span>
          </div>
        </div>
      </div>

      {/* Main chart container */}
      <div className="relative min-h-[300px] w-full">
        {isLoading && !invalidRange && (
          <div className="absolute inset-0 z-10 flex flex-col items-center justify-center gap-3 bg-white/70 backdrop-blur-[2px] transition">
            <div className="h-8 w-8 animate-spin rounded-full border-4 border-[#00babc] border-t-transparent" />
            <span className="text-xs font-medium text-slate-500">
              Chargement des données...
            </span>
          </div>
        )}

        {invalidRange && (
          <div role="alert" className="rounded-xl border border-amber-200 bg-amber-50 p-4 text-sm text-amber-800">
            {invalidRange}
          </div>
        )}

        {error && !invalidRange && (
          <div className="rounded-xl border border-red-200 bg-red-50 p-4 text-sm text-red-700">
            <p className="font-semibold">Erreur lors de la récupération des données</p>
            <p className="mt-0.5 text-xs text-red-600">{error}</p>
            <button
              type="button"
              onClick={handleRetry}
              className="mt-3 inline-flex items-center rounded-lg bg-red-600 px-3 py-1.5 text-xs font-semibold text-white transition hover:bg-red-700"
            >
              Réessayer
            </button>
          </div>
        )}

        {!error && !invalidRange && data && data.dailyBreakdown.length === 0 && (
          <div className="flex h-64 flex-col items-center justify-center rounded-xl border border-dashed border-slate-200 text-center">
            <p className="text-sm font-medium text-slate-600">
              Aucune annonce publiée pour cette période
            </p>
            <p className="mt-1 text-xs text-slate-400">
              Essayez d&apos;élargir l&apos;intervalle de dates pour voir plus de données.
            </p>
          </div>
        )}

        {!error && !invalidRange && data && data.dailyBreakdown.length > 0 && (
          <div className="h-72 w-full pt-2">
            <ResponsiveContainer width="100%" height="100%">
              {chartType === 'area' ? (
                <AreaChart
                  data={data.dailyBreakdown}
                  margin={{ top: 10, right: 10, left: -20, bottom: 0 }}
                >
                  <defs>
                    <linearGradient id="listingsDateGradient" x1="0" y1="0" x2="0" y2="1">
                      <stop offset="5%" stopColor="#00babc" stopOpacity={0.35} />
                      <stop offset="95%" stopColor="#00babc" stopOpacity={0.0} />
                    </linearGradient>
                  </defs>
                  <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="#f1f5f9" />
                  <XAxis
                    dataKey="date"
                    tickFormatter={formatXAxisDate}
                    tickLine={false}
                    axisLine={{ stroke: '#e2e8f0' }}
                    tick={{ fill: '#64748b', fontSize: 11 }}
                    minTickGap={24}
                  />
                  <YAxis
                    allowDecimals={false}
                    tickLine={false}
                    axisLine={false}
                    tick={{ fill: '#64748b', fontSize: 11 }}
                  />
                  <Tooltip content={<CustomTooltip />} />
                  <Area
                    type="monotone"
                    dataKey="count"
                    stroke="#00babc"
                    strokeWidth={2.5}
                    fill="url(#listingsDateGradient)"
                    activeDot={{ r: 5, fill: '#00babc', stroke: '#ffffff', strokeWidth: 2 }}
                  />
                </AreaChart>
              ) : (
                <BarChart
                  data={data.dailyBreakdown}
                  margin={{ top: 10, right: 10, left: -20, bottom: 0 }}
                >
                  <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="#f1f5f9" />
                  <XAxis
                    dataKey="date"
                    tickFormatter={formatXAxisDate}
                    tickLine={false}
                    axisLine={{ stroke: '#e2e8f0' }}
                    tick={{ fill: '#64748b', fontSize: 11 }}
                    minTickGap={24}
                  />
                  <YAxis
                    allowDecimals={false}
                    tickLine={false}
                    axisLine={false}
                    tick={{ fill: '#64748b', fontSize: 11 }}
                  />
                  <Tooltip content={<CustomTooltip />} />
                  <Bar
                    dataKey="count"
                    fill="#00babc"
                    radius={[4, 4, 0, 0]}
                    maxBarSize={40}
                  />
                </BarChart>
              )}
            </ResponsiveContainer>
          </div>
        )}
      </div>
    </div>
  );

  if (asCard) {
    return <Card className={className}>{content}</Card>;
  }

  return <div className={className}>{content}</div>;
}

export default ListingsBetweenDatesChart;
