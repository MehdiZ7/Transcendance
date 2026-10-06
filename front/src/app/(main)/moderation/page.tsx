'use client';

import { Suspense } from 'react';
import { useModeration } from '@/hooks/useModeration';
import { ToastAlert } from '@/components/moderation/ToastAlert';
import { ModerationTabs } from '@/components/moderation/ModerationTabs';
import { ModerationQueueTab } from '@/components/moderation/ModerationQueueTab';
import { ModerationHistoryTab } from '@/components/moderation/ModerationHistoryTab';
import { ModerationModals } from '@/components/moderation/ModerationModals';
import { UsersTable } from '@/components/moderation/UsersTable';
import { RoleGuard } from '@/components/auth/RoleGuard';
import type { UserRole } from '@/types/user';

function ModerationContent() {
  const {
    setActiveTab,
    isLoading,
    error,
    counts,
    currentQueueReports,
    currentQueueConfig,
    treatedReports,
    toastMessage,
    showToast,
    dismissToast,
    handleReject,
    handleDelete,
    handleBlockUser,
    handleReopen,
    reportToDelete,
    reportToBlock,
    reportToReopen,
    reportToReject,
    onCloseDelete,
    onConfirmDelete,
    onCloseBlock,
    onConfirmBlock,
    onCloseReopen,
    onConfirmReopen,
    onCloseReject,
    onConfirmReject,
    effectiveTab,
    isAdmin,
    currentUser,
  } = useModeration();

  return (
    <main className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8 space-y-6">
      {/* Toast alert message */}
      {toastMessage && (
        <ToastAlert message={toastMessage} onClose={dismissToast} />
      )}

      {/* Loading state */}
      {isLoading && (
        <div className="animate-pulse space-y-6">
          <div className="h-8 bg-slate-200 rounded-lg w-48"></div>
          <div className="h-12 bg-slate-100 rounded-xl"></div>
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
            <div className="h-64 bg-slate-100 rounded-2xl"></div>
            <div className="h-64 bg-slate-100 rounded-2xl"></div>
          </div>
        </div>
      )}

      {/* Error state */}
      {error && (
        <div className="p-4 bg-rose-50 border border-rose-200 rounded-xl text-sm text-rose-700">
          {error}
        </div>
      )}

      {!isLoading && !error && (
        <>
          {/* Main Tab Navigation */}
          <ModerationTabs
            activeTab={effectiveTab}
            onTabChange={setActiveTab}
            counts={counts}
            showHistory={isAdmin}
            showAdminUsers={isAdmin}
          />

          {/* Active Queue Views vs History View vs Admin Users View */}
          {effectiveTab === 'admin-users' ? (
            <UsersTable
              currentUserId={currentUser?.public_id}
              onToast={showToast}
            />
          ) : effectiveTab !== 'history' ? (
            <ModerationQueueTab
              reports={currentQueueReports}
              emptyTitle={currentQueueConfig.emptyTitle}
              emptyDescription={currentQueueConfig.emptyDescription}
              onReject={handleReject}
              onDelete={handleDelete}
              onBlockUser={handleBlockUser}
            />
          ) : (
            <ModerationHistoryTab
              reports={treatedReports}
              onReopen={handleReopen}
            />
          )}

          {/* Confirmation Modals */}
          <ModerationModals
            reportToDelete={reportToDelete}
            reportToBlock={reportToBlock}
            reportToReopen={reportToReopen}
            reportToReject={reportToReject}
            onCloseDelete={onCloseDelete}
            onConfirmDelete={onConfirmDelete}
            onCloseBlock={onCloseBlock}
            onConfirmBlock={onConfirmBlock}
            onCloseReopen={onCloseReopen}
            onConfirmReopen={onConfirmReopen}
            onCloseReject={onCloseReject}
            onConfirmReject={onConfirmReject}
          />
        </>
      )}
    </main>
  );
}
const MODERATION_ROLE: UserRole[] = ['moderator', 'admin']
export default function ModerationPage() {
  return (
    <Suspense
      fallback={
        <main className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
          <div className="animate-pulse space-y-6">
            <div className="h-8 bg-slate-200 rounded-lg w-48"></div>
            <div className="h-12 bg-slate-100 rounded-xl"></div>
            <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
              <div className="h-64 bg-slate-100 rounded-2xl"></div>
              <div className="h-64 bg-slate-100 rounded-2xl"></div>
            </div>
          </div>
        </main>
      }
    >
      <RoleGuard allowed={MODERATION_ROLE}>
        <ModerationContent />
      </RoleGuard>
    </Suspense>
  );
}
