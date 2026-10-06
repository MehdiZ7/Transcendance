import { Card } from '@/components/ui/Card';
import CategoryPieChart from '@/components/analytics/CategoryPieChart';
import SoldPercentagePieChart from '@/components/analytics/SoldPercentagePieChart';
import QuickStatsBar from '@/components/analytics/QuickStatsBar';
import ListingsBetweenDatesChart from '@/components/analytics/ListingsBetweenDatesChart';
import TopLikedListingsTable from '@/components/analytics/TopLikedListingsTable';
import ExportPdfButton from '@/components/analytics/ExportPdfButton';
import AnalyticsLiveIndicator from '@/components/analytics/AnalyticsLiveIndicator';
import { AnalyticsLiveProvider } from '@/context/AnalyticsLiveContext';
import { RoleGuard } from '@/components/auth/RoleGuard';
import type { UserRole } from '@/types/user';

const ADMIN_ROLE: UserRole[] = ['admin'];

export default function AnalyticsPage() {
  return (
    <RoleGuard allowed={ADMIN_ROLE}>
      <AnalyticsLiveProvider>
        <main className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8 space-y-8 print:p-0 print:m-0 print:max-w-none print:space-y-6">
          <div className="space-y-6">
            <div className="flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
              <div>
                <h1 className="text-2xl font-bold text-slate-900">
                  Dashboard
                </h1>
                <p className="text-xs text-slate-500 hidden print:block mt-1">
                  Rapport d&apos;activité LeBon42 • Analytics
                </p>
              </div>
              <div className="flex items-center gap-3">
                <AnalyticsLiveIndicator className="print:hidden" />
                <ExportPdfButton />
              </div>
            </div>

          {/* 5 cartes d'indicateurs rapides */}
          <QuickStatsBar />

          {/* Listings posted between two dates */}
          <Card>
            <ListingsBetweenDatesChart />
          </Card>

          {/* Graphiques Donut */}
          <div className="grid grid-cols-1 gap-6 lg:grid-cols-2 print:grid-cols-2">
            <Card>
              <CategoryPieChart />
            </Card>
            <Card>
              <SoldPercentagePieChart />
            </Card>
          </div>

          {/* Most-liked listings table */}
          <TopLikedListingsTable />

        </div>
      </main>
      </AnalyticsLiveProvider>
    </RoleGuard>
  );
}
