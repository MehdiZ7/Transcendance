'use client';

import { MAX_REPORT_REASON_LENGTH } from "@/lib/limits";
import React, { useState } from 'react';
import { Modal } from '@/components/ui/Modal';
import { Button } from '@/components/ui/Button';
import { reportsApi } from '@/lib/api/reports';
import type { CreateReportInput, Report, ReportTargetType } from '@/types/report';

export interface ReportModalProps {
  isOpen: boolean;
  onClose: () => void;
  targetType: ReportTargetType | string;
  targetId: string;
  targetTitle?: string;
  title?: string;
  onSubmit?: (data: CreateReportInput) => Promise<void> | void;
  onSuccess?: (report?: Report) => void;
}


export function ReportModal({
  isOpen,
  onClose,
  targetType,
  targetId,
  onSubmit,
  onSuccess,
}: ReportModalProps) {
  const [selectedCategory, setSelectedCategory] = useState<string | null>(null);
  const [message, setMessage] = useState('');
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [isSuccess, setIsSuccess] = useState(false);

  const handleReset = () => {
    setSelectedCategory(null);
    setMessage('');
    setError(null);
    setIsSubmitting(false);
    setIsSuccess(false);
  };

  const handleClose = () => {
    handleReset();
    onClose();
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();

    const trimmed = message.trim();
    if (!trimmed && !selectedCategory) {
      setError('Veuillez préciser le motif de votre signalement.');
      return;
    }

    if (trimmed.length > 0 && trimmed.length < 5) {
      setError('Veuillez fournir un message un peu plus détaillé (au moins 5 caractères).');
      return;
    }

    setIsSubmitting(true);
    setError(null);

    // Build the final reason description
    let fullReason = trimmed;
    if (selectedCategory) {
      fullReason = trimmed ? `[${selectedCategory}] ${trimmed}` : selectedCategory;
    }

    const payload: CreateReportInput = {
      target_type: (targetType as ReportTargetType),
      target_id: String(targetId),
      reason: fullReason,
    };

    try {
      let createdReport: Report | undefined;
      if (onSubmit) {
        await onSubmit(payload);
      } else {
        createdReport = await reportsApi.create(payload);
      }

      setIsSuccess(true);
      onSuccess?.(createdReport);
    } catch (err: unknown) {
      const errorMessage =
        err instanceof Error ? err.message : 'Une erreur est survenue lors de l\'envoi du signalement.';
      setError(errorMessage);
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <Modal isOpen={isOpen} onClose={handleClose} title="Signalement">
      {isSuccess ? (
        <div className="py-6 text-center space-y-4">
          <div className="w-14 h-14 mx-auto rounded-full bg-emerald-50 text-emerald-600 flex items-center justify-center ring-8 ring-emerald-50/50">
            <svg className="w-7 h-7" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2.5}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M4.5 12.75l6 6 9-13.5" />
            </svg>
          </div>

          <div className="space-y-1">
            <h4 className="text-base font-bold text-slate-900">Merci pour votre vigilance</h4>
            <p className="text-xs sm:text-sm text-slate-600 max-w-sm mx-auto leading-relaxed">
              Votre signalement a été transmis à l&apos;équipe de modération et sera traité rapidement afin de maintenir la sécurité de la communauté.
            </p>
          </div>

          <div className="pt-3">
            <Button
              type="button"
              variant="primary"
              size="md"
              onClick={handleClose}
              className="w-full sm:w-auto"
            >
              Fermer
            </Button>
          </div>
        </div>
      ) : (
        <form onSubmit={handleSubmit} className="space-y-4 pt-1">

          {/* Detailed message textarea */}
          <div className="space-y-1.5">
            <div className="flex items-center justify-between">
              <label htmlFor="report-message" className="text-xs font-bold text-slate-700 uppercase tracking-wider">
                Explications / Message <span className="text-rose-500">*</span>
              </label>
              <span className="text-[11px] text-slate-400 tabular-nums">
                {message.length} / 1000
              </span>
            </div>
            <textarea
              id="report-message"
              rows={4}
              maxLength={MAX_REPORT_REASON_LENGTH}
              value={message}
              onChange={(e) => {
                setMessage(e.target.value);
                if (error) setError(null);
              }}
              className="w-full text-xs sm:text-sm p-3 rounded-xl border border-slate-200 bg-white text-slate-800 placeholder:text-slate-400 focus:outline-none focus:border-[#00babc] focus:ring-2 focus:ring-[#00babc]/20 transition-all resize-none"
            />
          </div>

          {/* Error display */}
          {error && (
            <div className="text-xs text-rose-600 bg-rose-50 border border-rose-200/80 p-2.5 rounded-xl flex items-center gap-2">
              <svg className="w-4 h-4 shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                <path strokeLinecap="round" strokeLinejoin="round" d="M12 9v3.75m9-.75a9 9 0 11-18 0 9 9 0 0118 0zm-9 3.75h.008v.008H12v-.008z" />
              </svg>
              <span>{error}</span>
            </div>
          )}

          {/* Community safety notice */}
          <div className="flex items-start gap-2 text-[11px] sm:text-xs text-slate-500 bg-slate-50/80 border border-slate-200/60 p-2.5 rounded-xl">
            <svg className="w-4 h-4 text-slate-400 shrink-0 mt-0.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M11.25 11.25l.041-.02a.75.75 0 011.063.852l-.708 2.836a.75.75 0 001.063.853l.041-.021M21 12a9 9 0 11-18 0 9 9 0 0118 0zm-9-3.75h.008v.008H12V8.25z" />
            </svg>
            <p className="leading-snug">
              Ce signalement sera transmis aux modérateurs de la plateforme. Tout signalement abusif pourra faire l&apos;objet de sanctions.
            </p>
          </div>

          {/* Actions */}
          <div className="flex flex-col-reverse sm:flex-row items-center justify-end gap-2.5 pt-3 border-t border-slate-100">
            <Button
              type="button"
              variant="outline"
              size="sm"
              onClick={handleClose}
              disabled={isSubmitting}
              className="w-full sm:w-auto"
            >
              Annuler
            </Button>
            <Button
              type="submit"
              variant="danger"
              size="sm"
              isLoading={isSubmitting}
              disabled={isSubmitting}
              className="w-full sm:w-auto"
            >
              <svg className="w-3.5 h-3.5 mr-1" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                <path strokeLinecap="round" strokeLinejoin="round" d="M3 3v1.5M3 21v-6m0 0l2.77-.693a9 9 0 016.208.682l.108.054a9 9 0 006.086.71l3.114-.779V4.5l-3.114.779a9 9 0 01-6.086-.71l-.108-.054a9 9 0 00-6.208-.682L3 4.5M3 15V4.5" />
              </svg>
              <span>Envoyer le signalement</span>
            </Button>
          </div>
        </form>
      )}
    </Modal>
  );
}

export default ReportModal;

export { ReportButton } from './ReportButton';
export type { ReportButtonProps } from './ReportButton';
