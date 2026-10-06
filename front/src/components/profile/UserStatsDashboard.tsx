'use client';

import { useMemo, useSyncExternalStore } from 'react';
import {
  ResponsiveContainer,
  PieChart,
  Pie,
  Cell,
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
} from 'recharts';
import { Card } from '@/components/ui/Card';
import { Badge } from '@/components/ui/Badge';
import { Button } from '@/components/ui/Button';
import type { MyStats, SellingCategory, BuyingCategory } from '@/types';

interface UserStatsDashboardProps {
  stats: MyStats | null;
  isLoading?: boolean;
  error?: string | null;
  onRetry?: () => void;
}

const CATEGORY_COLORS = [
  '#00babc',
  '#3b82f6',
  '#10b981',
  '#f59e0b',
  '#8b5cf6',
  '#ec4899',
  '#6366f1',
  '#14b8a6',
];

interface DonutSlice {
  name: string;
  count: number;
  percentage: number;
  color: string;
}

interface TooltipPayloadItem {
  name?: string;
  value?: number;
  payload?: {
    name?: string;
    percentage?: number;
    count?: number;
    color?: string;
    total_spent?: number;
    [key: string]: unknown;
  };
}

const CustomPieTooltip = ({
  active,
  payload,
}: {
  active?: boolean;
  payload?: TooltipPayloadItem[];
}) => {
  if (!active || !payload || !payload.length || !payload[0].payload) return null;
  const item = payload[0].payload;

  return (
    <div className="relative z-50 rounded-xl border border-slate-200 bg-white/95 px-3 py-2 shadow-lg backdrop-blur-sm">
      <div className="flex items-center gap-2">
        <span
          className="h-2.5 w-2.5 rounded-full shrink-0 ring-2 ring-white"
          style={{ backgroundColor: item.color || '#00babc' }}
        />
        <span className="text-xs font-semibold text-slate-900">
          {item.name}
        </span>
      </div>
      <div className="mt-1 flex items-baseline gap-2 text-xs text-slate-500">
        <span className="text-sm font-bold text-slate-900">
          {item.percentage ?? item.count}%
        </span>
        <span>
          ({item.count} annonce{item.count && item.count > 1 ? 's' : ''})
        </span>
      </div>
    </div>
  );
};

const emptySubscribe = () => () => {};

export function UserStatsDashboard({
  stats,
  isLoading = false,
  error = null,
  onRetry,
}: UserStatsDashboardProps) {
  const mounted = useSyncExternalStore(
    emptySubscribe,
    () => true,
    () => false
  );

  // Selling stock breakdown (active vs sold)
  const stockChartData = useMemo<DonutSlice[]>(() => {
    if (!stats) return [];
    const activeCount = stats.selling.active.count;
    const soldCount = stats.selling.sold.count;
    const total = activeCount + soldCount;

    if (total === 0) return [];

    const soldPct = Math.round((soldCount / total) * 1000) / 10;
    const activePct = Math.max(0, Math.round((100 - soldPct) * 10) / 10);

    return [
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
    ].filter((s) => s.count > 0);
  }, [stats]);

  const soldPercentage = useMemo(() => {
    if (!stats) return 0;
    const total = stats.selling.active.count + stats.selling.sold.count;
    if (total === 0) return 0;
    return Math.round((stats.selling.sold.count / total) * 1000) / 10;
  }, [stats]);

  // Selling categories data formatted for BarChart
  const sellingCategoriesChartData = useMemo(() => {
    if (!stats?.selling.by_category) return [];
    return stats.selling.by_category.map((cat: SellingCategory) => ({
      name: cat.category_name || 'Autre',
      'En ligne': cat.active,
      Vendues: cat.sold,
      total: cat.active + cat.sold,
    }));
  }, [stats]);

  // Buying categories breakdown data
  const buyingCategoriesChartData = useMemo(() => {
    if (!stats?.buying.by_category) return [];
    const totalSpent = stats.buying.total_spent;
    return stats.buying.by_category.map((cat: BuyingCategory, idx: number) => {
      const percentage =
        totalSpent > 0 ? Math.round((cat.total_spent / totalSpent) * 1000) / 10 : 0;
      return {
        name: cat.category_name || 'Autre',
        count: cat.count,
        total_spent: cat.total_spent,
        percentage,
        color: CATEGORY_COLORS[idx % CATEGORY_COLORS.length],
      };
    });
  }, [stats]);

  if (isLoading) {
    return (
      <Card className="p-12 text-center">
        <div className="flex flex-col items-center justify-center gap-3">
          <div className="h-8 w-8 animate-spin rounded-full border-4 border-[#00babc] border-t-transparent" />
          <p className="text-sm font-medium text-slate-600">
            Chargement de vos statistiques d&apos;activité...
          </p>
        </div>
      </Card>
    );
  }

  if (error) {
    return (
      <Card className="p-8 border-red-200 bg-red-50/50">
        <div className="text-center space-y-3">
          <p className="font-semibold text-red-700">Impossible de charger vos statistiques</p>
          <p className="text-xs text-red-600">{error}</p>
          {onRetry && (
            <Button size="sm" variant="outline" onClick={onRetry} className="mt-2">
              Réessayer
            </Button>
          )}
        </div>
      </Card>
    );
  }

  if (!stats) {
    return null;
  }

  const totalSellingCreated = stats.selling.active.count + stats.selling.sold.count;
  const totalCatalogValue = stats.selling.active.total_value + stats.selling.sold.total_value;

  return (
    <div className="space-y-8">
      {/* SECTION 1: VENTES & STOCK */}
      <div className="space-y-4">
        <div>
          <div className="flex items-center gap-2">
            <h3 className="text-lg font-bold text-slate-900">Activité Vendeur</h3>
            <Badge variant="default" className="text-xs">
              {totalSellingCreated} annonce{totalSellingCreated > 1 ? 's' : ''} au total
            </Badge>
          </div>
          <p className="text-xs text-slate-500 mt-0.5">
            Suivi de votre stock, de vos annonces actives et de vos ventes finalisées.
          </p>
        </div>

        {/* KPIs Vente */}
        <div className="grid grid-cols-2 lg:grid-cols-4 gap-3 sm:gap-4">
          {/* Active Listings */}
          <Card className="p-4 bg-white border-slate-100 shadow-xs">
            <div className="flex items-center justify-between">
              <span className="text-xs font-medium text-slate-500">En ligne</span>
              <span className="h-2 w-2 rounded-full bg-blue-500" />
            </div>
            <div className="mt-2 flex items-baseline gap-2">
              <span className="text-2xl font-bold text-slate-900">
                {stats.selling.active.count}
              </span>
              <span className="text-xs text-slate-400">annonces</span>
            </div>
            <div className="mt-2 pt-2 border-t border-slate-100 text-[11px] text-slate-500 space-y-0.5">
              <div className="flex justify-between">
                <span>Valeur du stock :</span>
                <span className="font-semibold text-slate-700">{stats.selling.active.total_value} €</span>
              </div>
              <div className="flex justify-between">
                <span>Prix moyen :</span>
                <span className="font-semibold text-slate-700">{stats.selling.active.average_price} €</span>
              </div>
            </div>
          </Card>

          {/* Sold Listings */}
          <Card className="p-4 bg-white border-slate-100 shadow-xs">
            <div className="flex items-center justify-between">
              <span className="text-xs font-medium text-slate-500">Ventes finalisées</span>
              <span className="h-2 w-2 rounded-full bg-[#00babc]" />
            </div>
            <div className="mt-2 flex items-baseline gap-2">
              <span className="text-2xl font-bold text-[#00babc]">
                {stats.selling.sold.count}
              </span>
              <span className="text-xs text-slate-400">vendues</span>
            </div>
            <div className="mt-2 pt-2 border-t border-slate-100 text-[11px] text-slate-500 space-y-0.5">
              <div className="flex justify-between">
                <span>Total encaissé :</span>
                <span className="font-semibold text-[#00babc]">{stats.selling.sold.total_value} €</span>
              </div>
              <div className="flex justify-between">
                <span>Prix moyen :</span>
                <span className="font-semibold text-slate-700">{stats.selling.sold.average_price} €</span>
              </div>
            </div>
          </Card>

          {/* Taux de vente */}
          <Card className="p-4 bg-white border-slate-100 shadow-xs">
            <div className="flex items-center justify-between">
              <span className="text-xs font-medium text-slate-500">Taux de vente</span>
              <span className="h-2 w-2 rounded-full bg-emerald-500" />
            </div>
            <div className="mt-2 flex items-baseline gap-2">
              <span className="text-2xl font-bold text-emerald-600">
                {soldPercentage}%
              </span>
            </div>
            <div className="mt-2 pt-2 border-t border-slate-100 text-[11px] text-slate-500">
              <div className="flex justify-between">
                <span>Ratio vendues / total :</span>
                <span className="font-semibold text-slate-700">
                  {stats.selling.sold.count} / {totalSellingCreated}
                </span>
              </div>
            </div>
          </Card>

          {/* Chiffre d'affaires global */}
          <Card className="p-4 bg-white border-slate-100 shadow-xs">
            <div className="flex items-center justify-between">
              <span className="text-xs font-medium text-slate-500">Valeur totale créée</span>
              <span className="h-2 w-2 rounded-full bg-amber-500" />
            </div>
            <div className="mt-2 flex items-baseline gap-2">
              <span className="text-2xl font-bold text-slate-900">
                {totalCatalogValue} €
              </span>
            </div>
            <div className="mt-2 pt-2 border-t border-slate-100 text-[11px] text-slate-500">
              <div className="flex justify-between">
                <span>Ventes + En ligne</span>
                <span className="font-semibold text-slate-700">
                  {stats.selling.sold.total_value} € + {stats.selling.active.total_value} €
                </span>
              </div>
            </div>
          </Card>
        </div>

        {/* Charts Vente */}
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
          {/* Donut Chart: Vendues vs En ligne */}
          <Card className="p-6">
            <h4 className="text-sm font-semibold text-slate-900">Répartition des annonces</h4>
            <p className="text-xs text-slate-500 mb-4">Proportion des annonces vendues vs en ligne</p>

            {totalSellingCreated === 0 ? (
              <div className="py-12 text-center text-xs text-slate-400">
                Aucune annonce enregistrée à ce jour.
              </div>
            ) : mounted ? (
              <div>
                <div className="relative flex justify-center h-60 w-full">
                  <ResponsiveContainer width="100%" height="100%">
                    <PieChart>
                      <Pie
                        data={stockChartData}
                        dataKey="percentage"
                        nameKey="name"
                        cx="50%"
                        cy="50%"
                        outerRadius={90}
                        innerRadius={55}
                        paddingAngle={3}
                        stroke="#ffffff"
                        strokeWidth={2}
                      >
                        {stockChartData.map((entry) => (
                          <Cell key={`slice-${entry.name}`} fill={entry.color} />
                        ))}
                      </Pie>
                      <text
                        x="50%"
                        y="46%"
                        textAnchor="middle"
                        dominantBaseline="central"
                        style={{ fontSize: '24px', fontWeight: 700, fill: '#0f172a' }}
                      >
                        {soldPercentage}%
                      </text>
                      <text
                        x="50%"
                        y="58%"
                        textAnchor="middle"
                        dominantBaseline="central"
                        style={{
                          fontSize: '10px',
                          fontWeight: 600,
                          fill: '#94a3b8',
                          letterSpacing: '0.05em',
                        }}
                      >
                        VENDUES
                      </text>
                      <Tooltip content={<CustomPieTooltip />} />
                    </PieChart>
                  </ResponsiveContainer>
                </div>

                <div className="grid grid-cols-2 gap-3 pt-3 border-t border-slate-100">
                  <div className="rounded-lg bg-teal-50/50 p-2 text-center">
                    <div className="flex items-center justify-center gap-1.5 text-xs text-teal-800 font-medium">
                      <span className="h-2 w-2 rounded-full bg-[#00babc]" />
                      <span>Vendues</span>
                    </div>
                    <div className="mt-1 text-sm font-bold text-slate-900">
                      {stats.selling.sold.count} ({soldPercentage}%)
                    </div>
                  </div>
                  <div className="rounded-lg bg-blue-50/50 p-2 text-center">
                    <div className="flex items-center justify-center gap-1.5 text-xs text-blue-800 font-medium">
                      <span className="h-2 w-2 rounded-full bg-blue-500" />
                      <span>En ligne</span>
                    </div>
                    <div className="mt-1 text-sm font-bold text-slate-900">
                      {stats.selling.active.count} ({Math.max(0, Math.round((100 - soldPercentage) * 10) / 10)}%)
                    </div>
                  </div>
                </div>
              </div>
            ) : null}
          </Card>

          {/* Bar Chart: By Category */}
          <Card className="p-6">
            <h4 className="text-sm font-semibold text-slate-900">Annonces par catégorie</h4>
            <p className="text-xs text-slate-500 mb-4">Volume d&apos;annonces actives et vendues par catégorie</p>

            {sellingCategoriesChartData.length === 0 ? (
              <div className="py-12 text-center text-xs text-slate-400">
                Aucune catégorie renseignée pour l&apos;instant.
              </div>
            ) : mounted ? (
              <div>
                <div className="h-60 w-full">
                  <ResponsiveContainer width="100%" height="100%">
                    <BarChart
                      data={sellingCategoriesChartData}
                      margin={{ top: 10, right: 10, left: -20, bottom: 20 }}
                    >
                      <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="#f1f5f9" />
                      <XAxis
                        dataKey="name"
                        tick={{ fontSize: 11, fill: '#64748b' }}
                        interval={0}
                        angle={-15}
                        textAnchor="end"
                      />
                      <YAxis allowDecimals={false} tick={{ fontSize: 11, fill: '#64748b' }} />
                      <Tooltip
                        contentStyle={{
                          borderRadius: '0.75rem',
                          borderColor: '#e2e8f0',
                          fontSize: '12px',
                        }}
                      />
                      <Bar dataKey="Vendues" fill="#00babc" radius={[4, 4, 0, 0]} />
                      <Bar dataKey="En ligne" fill="#3b82f6" radius={[4, 4, 0, 0]} />
                    </BarChart>
                  </ResponsiveContainer>
                </div>

                <div className="flex items-center justify-center gap-6 pt-3 border-t border-slate-100 text-xs">
                  <div className="flex items-center gap-1.5">
                    <span className="h-2.5 w-2.5 rounded-sm bg-[#00babc]" />
                    <span className="text-slate-600">Vendues</span>
                  </div>
                  <div className="flex items-center gap-1.5">
                    <span className="h-2.5 w-2.5 rounded-sm bg-blue-500" />
                    <span className="text-slate-600">En ligne</span>
                  </div>
                </div>
              </div>
            ) : null}
          </Card>
        </div>

        {/* Per-category details (table) */}
        {stats.selling.by_category.length > 0 && (
          <Card className="overflow-hidden border-slate-100">
            <div className="p-4 border-b border-slate-100">
              <h4 className="text-xs font-semibold uppercase tracking-wider text-slate-500">
                Détail du catalogue par catégorie
              </h4>
            </div>
            <div className="overflow-x-auto">
              <table className="w-full text-left text-xs">
                <thead className="bg-slate-50 text-slate-500 border-b border-slate-100">
                  <tr>
                    <th className="py-2.5 px-4 font-medium">Catégorie</th>
                    <th className="py-2.5 px-4 font-medium text-center">En ligne</th>
                    <th className="py-2.5 px-4 font-medium text-center">Vendues</th>
                    <th className="py-2.5 px-4 font-medium text-right">Total</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-100 text-slate-700">
                  {stats.selling.by_category.map((cat: SellingCategory) => (
                    <tr key={cat.category_id ?? 'none'} className="hover:bg-slate-50/50">
                      <td className="py-2.5 px-4 font-medium text-slate-900">
                        {cat.category_name || 'Non catégorisé'}
                      </td>
                      <td className="py-2.5 px-4 text-center">
                        <span className="inline-block px-2 py-0.5 rounded-full bg-blue-50 text-blue-700 font-semibold">
                          {cat.active}
                        </span>
                      </td>
                      <td className="py-2.5 px-4 text-center">
                        <span className="inline-block px-2 py-0.5 rounded-full bg-teal-50 text-teal-700 font-semibold">
                          {cat.sold}
                        </span>
                      </td>
                      <td className="py-2.5 px-4 text-right font-bold text-slate-900">
                        {cat.active + cat.sold}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </Card>
        )}
      </div>

      {/* SECTION 2: ACHATS */}
      <div className="space-y-4 pt-4 border-t border-slate-200">
        <div>
          <div className="flex items-center gap-2">
            <h3 className="text-lg font-bold text-slate-900">Activité Acheteur</h3>
            <Badge variant="default" className="text-xs">
              {stats.buying.count} achat{stats.buying.count > 1 ? 's' : ''}
            </Badge>
          </div>
          <p className="text-xs text-slate-500 mt-0.5">
            Historique et récapitulatif financier de vos acquisitions sur LeBon42.
          </p>
        </div>

        {/* KPIs Achats */}
        <div className="grid grid-cols-1 sm:grid-cols-3 gap-3 sm:gap-4">
          <Card className="p-4 bg-white border-slate-100 shadow-xs">
            <span className="text-xs font-medium text-slate-500">Articles achetés</span>
            <div className="mt-2 flex items-baseline gap-2">
              <span className="text-2xl font-bold text-slate-900">{stats.buying.count}</span>
              <span className="text-xs text-slate-400">au total</span>
            </div>
          </Card>

          <Card className="p-4 bg-white border-slate-100 shadow-xs">
            <span className="text-xs font-medium text-slate-500">Total dépensé</span>
            <div className="mt-2 flex items-baseline gap-2">
              <span className="text-2xl font-bold text-[#00babc]">{stats.buying.total_spent} €</span>
            </div>
          </Card>

          <Card className="p-4 bg-white border-slate-100 shadow-xs">
            <span className="text-xs font-medium text-slate-500">Panier moyen</span>
            <div className="mt-2 flex items-baseline gap-2">
              <span className="text-2xl font-bold text-slate-900">{stats.buying.average_price} €</span>
              <span className="text-xs text-slate-400">/ article</span>
            </div>
          </Card>
        </div>

        {/* Purchases breakdown by category */}
        {stats.buying.count === 0 ? (
          <Card className="p-8 text-center bg-slate-50/50 border-dashed border-slate-200">
            <div className="max-w-md mx-auto space-y-3">
              <p className="text-sm font-semibold text-slate-700">
                Vous n&apos;avez pas encore effectué d&apos;achats
              </p>
              <p className="text-xs text-slate-500">
                Dès qu&apos;un vendeur aura validé la vente d&apos;un article en votre faveur,
                vos statistiques d&apos;achats apparaîtront automatiquement ici.
              </p>
              <div className="pt-2">
                <Button href="/listings" size="sm" variant="primary">
                  Explorer les annonces
                </Button>
              </div>
            </div>
          </Card>
        ) : (
          <Card className="p-6">
            <h4 className="text-sm font-semibold text-slate-900 mb-1">
              Dépenses par catégorie
            </h4>
            <p className="text-xs text-slate-500 mb-6">
              Répartition des montants investis par catégorie d&apos;articles achetés
            </p>

            <div className="grid grid-cols-1 md:grid-cols-2 gap-6 items-center">
              {/* Category list with visual progress bars */}
              <div className="space-y-3">
                {buyingCategoriesChartData.map((cat) => (
                  <div key={cat.name} className="space-y-1">
                    <div className="flex items-center justify-between text-xs">
                      <div className="flex items-center gap-2">
                        <span
                          className="h-2.5 w-2.5 rounded-full shrink-0"
                          style={{ backgroundColor: cat.color }}
                        />
                        <span className="font-medium text-slate-800">{cat.name}</span>
                        <span className="text-[11px] text-slate-400">
                          ({cat.count} article{cat.count > 1 ? 's' : ''})
                        </span>
                      </div>
                      <div className="flex items-center gap-2">
                        <span className="font-semibold text-slate-900">{cat.total_spent} €</span>
                        <span className="text-[11px] text-slate-400 w-10 text-right">
                          {cat.percentage}%
                        </span>
                      </div>
                    </div>
                    <div className="h-1.5 w-full rounded-full bg-slate-100 overflow-hidden">
                      <div
                        className="h-full rounded-full transition-all duration-500"
                        style={{
                          width: `${cat.percentage}%`,
                          backgroundColor: cat.color,
                        }}
                      />
                    </div>
                  </div>
                ))}
              </div>

              {/* Mini Donut of spending */}
              {mounted && (
                <div className="relative flex justify-center h-48 w-full">
                  <ResponsiveContainer width="100%" height="100%">
                    <PieChart>
                      <Pie
                        data={buyingCategoriesChartData}
                        dataKey="total_spent"
                        nameKey="name"
                        cx="50%"
                        cy="50%"
                        outerRadius={75}
                        innerRadius={45}
                        paddingAngle={3}
                        stroke="#ffffff"
                        strokeWidth={2}
                      >
                        {buyingCategoriesChartData.map((entry) => (
                          <Cell key={`buying-${entry.name}`} fill={entry.color} />
                        ))}
                      </Pie>
                      <text
                        x="50%"
                        y="46%"
                        textAnchor="middle"
                        dominantBaseline="central"
                        style={{ fontSize: '18px', fontWeight: 700, fill: '#0f172a' }}
                      >
                        {stats.buying.total_spent} €
                      </text>
                      <text
                        x="50%"
                        y="58%"
                        textAnchor="middle"
                        dominantBaseline="central"
                        style={{
                          fontSize: '9px',
                          fontWeight: 600,
                          fill: '#94a3b8',
                          letterSpacing: '0.05em',
                        }}
                      >
                        DÉPENSÉ
                      </text>
                      <Tooltip
                        content={({ active, payload }) => {
                          if (!active || !payload || !payload.length) return null;
                          const p = payload[0].payload;
                          return (
                            <div className="rounded-xl border border-slate-200 bg-white/95 px-3 py-2 shadow-lg backdrop-blur-sm text-xs">
                              <span className="font-semibold text-slate-900">{p.name}</span>
                              <div className="text-slate-500 mt-0.5">
                                {p.total_spent} € ({p.percentage}%) • {p.count} article(s)
                              </div>
                            </div>
                          );
                        }}
                      />
                    </PieChart>
                  </ResponsiveContainer>
                </div>
              )}
            </div>
          </Card>
        )}
      </div>
    </div>
  );
}
