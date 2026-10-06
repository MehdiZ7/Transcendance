'use client';

import { useState, useMemo, useEffect } from 'react';
import { useSearchParams } from 'next/navigation';
import { reportsApi } from '@/lib/api/reports';
import {
  getTargetUser,
  isReportTreated,
  type ModerationCounts,
  type ModerationTab,
  type QueueConfig,
} from '@/components/moderation/types';
import type { Report } from '@/types/report';
import type { UserProfile } from '@/types/user';
import { usersApi } from '@/lib/api/users';

export const QUEUE_CONFIGS: Record<
  Exclude<ModerationTab, 'history' | 'admin-users'>,
  QueueConfig
> = {
  listings: {
    emptyTitle: "Aucun signalement d'annonce en attente",
    emptyDescription:
      "Toutes les annonces signalées ont été examinées et traitées. Vous pouvez consulter les anciennes demandes dans l'onglet Historique.",
  },
  messages: {
    emptyTitle: "Aucun signalement de message en attente",
    emptyDescription:
      "Tous les messages signalés ont été traités. Les résolutions précédentes sont archivées dans l'onglet Historique.",
  },
  users: {
    emptyTitle: "Aucun signalement d'utilisateur en attente",
    emptyDescription:
      "Tous les profils et comportements signalés ont été examinés et traités. Vous pouvez consulter les anciennes décisions dans l'onglet Historique.",
  },
  reviews: {
    emptyTitle: "Aucun signalement d'avis en attente",
    emptyDescription:
      "Tous les avis signalés ont été examinés et traités. Vous pouvez consulter les anciennes décisions dans l'onglet Historique.",
  },
};

export function useModeration() {
  const searchParams = useSearchParams();
  const initialTabParam =
    searchParams.get('tab') || searchParams.get('target_type');

  const defaultTab: ModerationTab = useMemo(() => {
    if (initialTabParam === 'message' || initialTabParam === 'messages')
      return 'messages';
    if (
      initialTabParam === 'user' ||
      initialTabParam === 'users' ||
      initialTabParam === 'utilisateurs'
    )
      return 'users';
    if (
      initialTabParam === 'review' ||
      initialTabParam === 'reviews' ||
      initialTabParam === 'avis'
    )
      return 'reviews';
    if (initialTabParam === 'history' || initialTabParam === 'historique')
      return 'history';
    if (
      initialTabParam === 'admin-users' ||
      initialTabParam === 'admin_users' ||
      initialTabParam === 'comptes' ||
      initialTabParam === 'roles' ||
      initialTabParam === 'gestion-comptes' ||
      initialTabParam === 'gestion-utilisateurs'
    )
      return 'admin-users';
    return 'listings';
  }, [initialTabParam]);

  const [activeTab, setActiveTab] = useState<ModerationTab>(defaultTab);
  const [reports, setReports] = useState<Report[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [isAdmin, setIsAdmin] = useState(false);
  const [currentUser, setCurrentUser] = useState<UserProfile | null>(null);

  useEffect(() => {
    usersApi.getCurrent()
      .then((me) => {
        if (!me) {
          setCurrentUser(null);
          setIsAdmin(false);
          return;
        }
        setCurrentUser(me);
        setIsAdmin(me.role === 'admin');
      })
      .catch(() => {
        setCurrentUser(null);
        setIsAdmin(false);
      });
  }, []);

  // Security: non-admin cannot access the history or admin-users tabs
  const effectiveTab: ModerationTab =
    !isAdmin && (activeTab === 'history' || activeTab === 'admin-users')
      ? 'listings'
      : activeTab;

  useEffect(() => {
    reportsApi.getAll()
      .then((data) => setReports(data))
      .catch((err: unknown) => {
        setError(err instanceof Error ? err.message : 'Impossible de charger les signalements');
      })
      .finally(() => setIsLoading(false));
  }, []);

  // Modals state
  const [reportToDelete, setReportToDelete] = useState<Report | null>(null);
  const [reportToBlock, setReportToBlock] = useState<Report | null>(null);
  const [reportToReopen, setReportToReopen] = useState<Report | null>(null);
  const [reportToReject, setReportToReject] = useState<Report | null>(null);

  // Toast notification state
  const [toastMessage, setToastMessage] = useState<string | null>(null);

  const showToast = (message: string) => {
    setToastMessage(message);
    setTimeout(() => {
      setToastMessage((prev) => (prev === message ? null : prev));
    }, 4500);
  };

  const dismissToast = () => setToastMessage(null);

  // Queues derivation
  const pendingListingReports = useMemo(
    () =>
      reports.filter(
        (r) =>
          r.target_type === 'listing' && !isReportTreated(r)
      ),
    [reports]
  );

  const pendingMessageReports = useMemo(
    () =>
      reports.filter(
        (r) =>
          r.target_type === 'message' && !isReportTreated(r)
      ),
    [reports]
  );

  const pendingUserReports = useMemo(
    () =>
      reports.filter(
        (r) => r.target_type === 'user' && !isReportTreated(r)
      ),
    [reports]
  );

  const pendingReviewReports = useMemo(
    () =>
      reports.filter(
        (r) => r.target_type === 'review' && !isReportTreated(r)
      ),
    [reports]
  );

  const treatedReports = useMemo(
    () =>
      reports
        .filter(isReportTreated)
        .sort((a, b) => {
          const dateA = new Date(a.closed_at || a.created_at).getTime();
          const dateB = new Date(b.closed_at || b.created_at).getTime();
          return dateB - dateA;
        }),
    [reports]
  );

  const counts: ModerationCounts = useMemo(
    () => ({
      listings: pendingListingReports.length,
      messages: pendingMessageReports.length,
      users: pendingUserReports.length,
      reviews: pendingReviewReports.length,
      history: treatedReports.length,
    }),
    [
      pendingListingReports.length,
      pendingMessageReports.length,
      pendingUserReports.length,
      pendingReviewReports.length,
      treatedReports.length,
    ]
  );

  const currentQueueReports = useMemo(() => {
    switch (effectiveTab) {
      case 'listings':
        return pendingListingReports;
      case 'messages':
        return pendingMessageReports;
      case 'users':
        return pendingUserReports;
      case 'reviews':
        return pendingReviewReports;
      default:
        return [];
    }
  }, [
    effectiveTab,
    pendingListingReports,
    pendingMessageReports,
    pendingUserReports,
    pendingReviewReports,
  ]);

  const currentQueueConfig = useMemo(() => {
    if (effectiveTab === 'history' || effectiveTab === 'admin-users') {
      return {
        emptyTitle: '',
        emptyDescription: '',
      };
    }
    return QUEUE_CONFIGS[effectiveTab];
  }, [effectiveTab]);

  // Action handlers
  const handleReject = (report: Report) => {
    setReportToReject(report);
  };

  const handleConfirmReject = async () => {
    if (!reportToReject) return;
    const report = reportToReject;
    setReportToReject(null);

    try {
      const updated = await reportsApi.reject(report.id);
      setReports((prev) =>
        prev.map((r) => (r.id === report.id ? { ...r, ...updated } : r))
      );
      showToast(
        `Le signalement #${report.id.slice(
          -8
        )} a été rejeté et archivé dans l'historique.`
      );
    } catch (err) {
      showToast(
        err instanceof Error ? err.message : "Erreur lors du rejet du signalement."
      );
    }
  };

  const handleDelete = (report: Report) => {
    setReportToDelete(report);
  };

  const handleConfirmDelete = async () => {
    if (!reportToDelete) return;
    const report = reportToDelete;
    const isListing = report.target_type === 'listing';
    const isMessage = report.target_type === 'message';
    const isUser = report.target_type === 'user';
    const isReview = report.target_type === 'review';
    setReportToDelete(null);

    try {
      const updated = await reportsApi.deleteTarget(report.id, report.target_type, report.target_id);
      setReports((prev) =>
        prev.map((r) =>
          r.id === report.id
            ? {
                ...r,
                ...updated,
                target:
                  isUser && r.target ? { ...r.target, is_active: false } : undefined,
              }
            : r
        )
      );

      showToast(
        `${isListing
          ? "L'annonce a été supprimée"
          : isMessage
            ? 'Le message a été supprimé'
            : isUser
              ? "L'utilisateur a été suspendu"
              : isReview
                ? "L'avis a été supprimé"
                : 'Le contenu a été supprimé'
        }. Le signalement #${report.id.slice(-8)} est désormais classé comme résolu.`
      );
    } catch (err) {
      showToast(
        err instanceof Error ? err.message : "Erreur lors de la suppression du contenu."
      );
    }
  };

  const handleBlockUser = (report: Report) => {
    setReportToBlock(report);
  };

  const handleConfirmBlockUser = async () => {
    if (!reportToBlock) return;
    const report = reportToBlock;
    const targetUser = getTargetUser(report);
    const userName = targetUser?.display_name || 'Cet utilisateur';
    const userId = targetUser?.id || targetUser?.public_id || report.target_id;
    setReportToBlock(null);

    try {
      const updated = await reportsApi.blockUser(report.id, userId);
      setReports((prev) =>
        prev.map((r) =>
          r.id === report.id
            ? {
                ...r,
                ...updated,
                target: r.target ? { ...r.target, is_active: false } : r.target,
              }
            : r
        )
      );

      showToast(
        `L'utilisateur ${userName} a été bloqué avec succès. Le signalement #${report.id.slice(
          -8
        )} est désormais classé comme résolu.`
      );
    } catch (err) {
      showToast(
        err instanceof Error ? err.message : "Erreur lors du blocage de l'utilisateur."
      );
    }
  };

  const handleReopen = (report: Report) => {
    setReportToReopen(report);
  };

  const handleConfirmReopen = async () => {
    if (!reportToReopen) return;
    const report = reportToReopen;
    const isUser = report.target_type === 'user';
    const targetUser = getTargetUser(report);
    const userName = targetUser?.display_name || "l'utilisateur";
    const userId = targetUser?.id || targetUser?.public_id || report.target_id;
    setReportToReopen(null);

    try {
      const updated = isUser
        ? await reportsApi.unblockUser(report.id, userId)
        : await reportsApi.reopen(report.id);

      setReports((prev) =>
        prev.map((r) =>
          r.id === report.id
            ? {
                ...r,
                ...updated,
                target:
                  isUser && r.target ? { ...r.target, is_active: true } : r.target,
              }
            : r
        )
      );

      if (isUser) {
        showToast(
          `L'utilisateur ${userName} a été débloqué et le signalement #${report.id.slice(
            -8
          )} a été réintégré dans la file d'attente.`
        );
      } else {
        showToast(
          `Le signalement #${report.id.slice(
            -8
          )} a été rouvert et réintégré dans la file d'attente.`
        );
      }
    } catch (err) {
      showToast(
        err instanceof Error ? err.message : "Erreur lors de la réouverture du signalement."
      );
    }
  };

  return {
    activeTab,
    effectiveTab,
    isAdmin,
    currentUser,
    setActiveTab,
    reports,
    isLoading,
    error,
    counts,
    currentQueueReports,
    currentQueueConfig,
    treatedReports,
    toastMessage,
    showToast,
    dismissToast,
    // Action triggers for cards
    handleReject,
    handleDelete,
    handleBlockUser,
    handleReopen,
    // Modals state & handlers
    reportToDelete,
    reportToBlock,
    reportToReopen,
    reportToReject,
    onCloseDelete: () => setReportToDelete(null),
    onConfirmDelete: handleConfirmDelete,
    onCloseBlock: () => setReportToBlock(null),
    onConfirmBlock: handleConfirmBlockUser,
    onCloseReopen: () => setReportToReopen(null),
    onConfirmReopen: handleConfirmReopen,
    onCloseReject: () => setReportToReject(null),
    onConfirmReject: handleConfirmReject,
  };
}
