import { useState, useMemo } from 'react';
import { Card } from '@/components/ui/Card';
import { Button } from '@/components/ui/Button';
import { ReportCard } from './ReportCard';
import type { Report } from '@/types/report';
import type { HistoryStatusFilter, HistoryTypeFilter } from './types';

interface ModerationHistoryTabProps {
  reports: Report[];
  onReopen: (report: Report) => void;
}

export function ModerationHistoryTab({
  reports,
  onReopen,
}: ModerationHistoryTabProps) {
  const [historyTypeFilter, setHistoryTypeFilter] =
    useState<HistoryTypeFilter>('all');
  const [historyStatusFilter, setHistoryStatusFilter] =
    useState<HistoryStatusFilter>('all');
  const [historySearchQuery, setHistorySearchQuery] = useState('');

  const filteredReports = useMemo(() => {
    return reports.filter((report) => {
      const type = report.target_type;
      const status = report.status;

      // Type filter
      if (historyTypeFilter === 'listing' && type !== 'listing') return false;
      if (historyTypeFilter === 'message' && type !== 'message') return false;
      if (historyTypeFilter === 'user' && type !== 'user') return false;
      if (historyTypeFilter === 'review' && type !== 'review') return false;

      // Status filter
      if (historyStatusFilter === 'resolved' && status !== 'resolved') return false;
      if (historyStatusFilter === 'closed' && status !== 'closed') return false;

      // Search query filter
      if (historySearchQuery.trim()) {
        const q = historySearchQuery.toLowerCase().trim();
        const reasonMatches = report.reason?.toLowerCase().includes(q);
        const idMatches = String(report.id).toLowerCase().includes(q);
        const reporterMatches = report.reporter?.display_name
          ?.toLowerCase()
          .includes(q);
        return reasonMatches || idMatches || reporterMatches;
      }

      return true;
    });
  }, [reports, historyTypeFilter, historyStatusFilter, historySearchQuery]);

  const hasActiveFilters =
    historySearchQuery !== '' ||
    historyTypeFilter !== 'all' ||
    historyStatusFilter !== 'all';

  const resetFilters = () => {
    setHistoryTypeFilter('all');
    setHistoryStatusFilter('all');
    setHistorySearchQuery('');
  };

  return (
    <section className="space-y-6">
      {/* History Header & Controls */}
      <div className="space-y-4">
        {/* Filter Controls Bar */}
        <div className="flex flex-col lg:flex-row lg:items-center justify-between gap-3 bg-slate-50 border border-slate-200/80 rounded-2xl p-3 sm:p-4">
          {/* Type Filters */}
          <div className="flex flex-wrap items-center gap-1.5 text-xs">
            <span className="text-slate-500 font-medium mr-1 hidden sm:inline">
              Type :
            </span>
            <button
              type="button"
              onClick={() => setHistoryTypeFilter('all')}
              className={`px-3 py-1.5 rounded-lg font-semibold transition-colors cursor-pointer ${
                historyTypeFilter === 'all'
                  ? 'bg-slate-900 text-white'
                  : 'bg-white text-slate-700 border border-slate-200 hover:bg-slate-100'
              }`}
            >
              Tous ({reports.length})
            </button>
            <button
              type="button"
              onClick={() => setHistoryTypeFilter('listing')}
              className={`px-3 py-1.5 rounded-lg font-semibold transition-colors cursor-pointer ${
                historyTypeFilter === 'listing'
                  ? 'bg-slate-900 text-white'
                  : 'bg-white text-slate-700 border border-slate-200 hover:bg-slate-100'
              }`}
            >
              Annonces (
              {
                reports.filter(
                  (r) => r.target_type === 'listing'
                ).length
              }
              )
            </button>
            <button
              type="button"
              onClick={() => setHistoryTypeFilter('message')}
              className={`px-3 py-1.5 rounded-lg font-semibold transition-colors cursor-pointer ${
                historyTypeFilter === 'message'
                  ? 'bg-slate-900 text-white'
                  : 'bg-white text-slate-700 border border-slate-200 hover:bg-slate-100'
              }`}
            >
              Messages (
              {
                reports.filter(
                  (r) => r.target_type === 'message'
                ).length
              }
              )
            </button>
            <button
              type="button"
              onClick={() => setHistoryTypeFilter('user')}
              className={`px-3 py-1.5 rounded-lg font-semibold transition-colors cursor-pointer ${
                historyTypeFilter === 'user'
                  ? 'bg-slate-900 text-white'
                  : 'bg-white text-slate-700 border border-slate-200 hover:bg-slate-100'
              }`}
            >
              Utilisateurs (
              {
                reports.filter(
                  (r) => r.target_type === 'user'
                ).length
              }
              )
            </button>
            <button
              type="button"
              onClick={() => setHistoryTypeFilter('review')}
              className={`px-3 py-1.5 rounded-lg font-semibold transition-colors cursor-pointer ${
                historyTypeFilter === 'review'
                  ? 'bg-slate-900 text-white'
                  : 'bg-white text-slate-700 border border-slate-200 hover:bg-slate-100'
              }`}
            >
              Avis (
              {
                reports.filter(
                  (r) => r.target_type === 'review'
                ).length
              }
              )
            </button>
          </div>

          {/* Status & Search Filter */}
          <div className="flex flex-wrap items-center gap-2">
            <div className="flex items-center gap-1.5 text-xs">
              <span className="text-slate-500 font-medium mr-1 hidden sm:inline">
                Statut :
              </span>
              <button
                type="button"
                onClick={() => setHistoryStatusFilter('all')}
                className={`px-2.5 py-1 rounded-md text-xs font-medium transition-colors cursor-pointer ${
                  historyStatusFilter === 'all'
                    ? 'bg-slate-200 text-slate-900 font-bold'
                    : 'text-slate-600 hover:text-slate-900'
                }`}
              >
                Tous
              </button>
              <button
                type="button"
                onClick={() => setHistoryStatusFilter('resolved')}
                className={`px-2.5 py-1 rounded-md text-xs font-medium transition-colors cursor-pointer ${
                  historyStatusFilter === 'resolved'
                    ? 'bg-emerald-100 text-emerald-800 font-bold'
                    : 'text-slate-600 hover:text-emerald-700'
                }`}
              >
                Résolus
              </button>
              <button
                type="button"
                onClick={() => setHistoryStatusFilter('closed')}
                className={`px-2.5 py-1 rounded-md text-xs font-medium transition-colors cursor-pointer ${
                  historyStatusFilter === 'closed'
                    ? 'bg-rose-100 text-rose-800 font-bold'
                    : 'text-slate-600 hover:text-rose-700'
                }`}
              >
                Rejetés
              </button>
            </div>

            {/* Quick Search */}
            <div className="relative flex-1 sm:w-48">
              <input
                type="text"
                value={historySearchQuery}
                onChange={(e) => setHistorySearchQuery(e.target.value)}
                placeholder="Filtrer par mot-clé..."
                className="w-full text-xs pl-7 pr-2.5 py-1.5 rounded-lg border border-slate-200 bg-white text-slate-800 focus:outline-none focus:border-[#00babc]"
              />
              <svg
                className="w-3.5 h-3.5 text-slate-400 absolute left-2 top-2.5 pointer-events-none"
                fill="none"
                viewBox="0 0 24 24"
                stroke="currentColor"
                strokeWidth={2}
              >
                <path
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  d="M21 21l-5.197-5.197m0 0A7.5 7.5 0 105.196 5.196a7.5 7.5 0 0010.607 10.607z"
                />
              </svg>
              {historySearchQuery && (
                <button
                  type="button"
                  onClick={() => setHistorySearchQuery('')}
                  className="absolute right-2 top-2 text-slate-400 hover:text-slate-600 text-xs cursor-pointer"
                >
                  ✕
                </button>
              )}
            </div>
          </div>
        </div>
      </div>

      {/* History List */}
      {filteredReports.length === 0 ? (
        <Card className="text-center py-12 px-4">
          <div className="w-12 h-12 rounded-full bg-slate-100 text-slate-400 flex items-center justify-center mx-auto mb-3">
            <svg
              className="w-6 h-6"
              fill="none"
              viewBox="0 0 24 24"
              stroke="currentColor"
              strokeWidth={2}
            >
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                d="M12 6v6h4.5m4.5 0a9 9 0 11-18 0 9 9 0 0118 0z"
              />
            </svg>
          </div>
          <h3 className="text-sm font-bold text-slate-900">
            Aucune demande traitée trouvée
          </h3>
          <p className="text-xs text-slate-500 mt-1 max-w-sm mx-auto">
            {hasActiveFilters
              ? 'Aucun signalement ne correspond à vos critères de recherche dans l’historique.'
              : 'Les demandes rejetées ou résolues apparaîtront ici au fur et à mesure de vos actions.'}
          </p>
          {hasActiveFilters && (
            <Button
              variant="outline"
              size="sm"
              onClick={resetFilters}
              className="mt-4 text-xs"
            >
              Réinitialiser les filtres
            </Button>
          )}
        </Card>
      ) : (
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6 items-stretch">
          {filteredReports.map((report) => (
            <ReportCard key={report.id} report={report} onReopen={onReopen} />
          ))}
        </div>
      )}
    </section>
  );
}
