import { Card } from '@/components/ui/Card';
import { ReportCard } from './ReportCard';
import type { Report } from '@/types/report';

interface ModerationQueueTabProps {
  reports: Report[];
  emptyTitle: string;
  emptyDescription: string;
  onReject?: (report: Report) => void;
  onDelete?: (report: Report) => void;
  onBlockUser?: (report: Report) => void;
}

export function ModerationQueueTab({
  reports,
  emptyTitle,
  emptyDescription,
  onReject,
  onDelete,
  onBlockUser,
}: ModerationQueueTabProps) {
  if (reports.length === 0) {
    return (
      <section className="space-y-4">
        <Card className="text-center py-12 px-4">
          <div className="w-12 h-12 rounded-full bg-emerald-50 text-emerald-600 flex items-center justify-center mx-auto mb-3">
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
                d="M4.5 12.75l6 6 9-13.5"
              />
            </svg>
          </div>
          <h3 className="text-sm font-bold text-slate-900">{emptyTitle}</h3>
          <p className="text-xs text-slate-500 mt-1 max-w-sm mx-auto">
            {emptyDescription}
          </p>
        </Card>
      </section>
    );
  }

  return (
    <section className="space-y-4">
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6 items-stretch">
        {reports.map((report) => (
          <ReportCard
            key={report.id}
            report={report}
            onReject={onReject}
            onDelete={onDelete}
            onBlockUser={onBlockUser}
          />
        ))}
      </div>
    </section>
  );
}
