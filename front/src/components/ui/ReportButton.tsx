'use client';

import React, { useState } from 'react';
import { ReportModal } from './ReportModal';
import { Button, type ButtonVariant, type ButtonSize } from './Button';
import type { CreateReportInput, Report, ReportTargetType } from '@/types/report';
import { useCurrentUser } from '@/hooks/useCurrentUser';
import { useAuthModal } from '@/context/AuthModalContext';

export interface ReportButtonProps {
  targetType: ReportTargetType | string;
  targetId: string;
  targetTitle?: string;
  label?: string;
  variant?: 'link' | 'button' | 'icon';
  buttonVariant?: ButtonVariant;
  buttonSize?: ButtonSize;
  className?: string;
  onSuccess?: (report?: Report) => void;
  onSubmit?: (data: CreateReportInput) => Promise<void> | void;
}

export function ReportButton({
  targetType,
  targetId,
  targetTitle,
  label,
  variant = 'link',
  buttonVariant = 'outline',
  buttonSize = 'sm',
  className = '',
  onSuccess,
  onSubmit,
}: ReportButtonProps) {
  const { user } = useCurrentUser();
  const { openAuthModal } = useAuthModal();
  const [isOpen, setIsOpen] = useState(false);

  const handleOpen = (e?: React.MouseEvent) => {
    e?.preventDefault();
    e?.stopPropagation();
    if (!user) {
      openAuthModal();
      return;
    }
    setIsOpen(true);
  };

  const defaultLabel =
    targetType === 'listing'
      ? 'Signaler cette annonce'
      : targetType === 'message'
      ? 'Signaler ce message'
      : targetType === 'user'
      ? 'Signaler cet utilisateur'
      : 'Signaler';

  const buttonText = label || defaultLabel;

  return (
    <>
      {variant === 'link' && (
        <button
          type="button"
          onClick={handleOpen}
          className={`inline-flex items-center gap-1.5 text-xs text-slate-400 hover:text-rose-600 transition-colors cursor-pointer select-none ${className}`}
        >
          <svg
            className="w-3.5 h-3.5 shrink-0"
            fill="none"
            viewBox="0 0 24 24"
            stroke="currentColor"
            strokeWidth={2}
          >
            <path
              strokeLinecap="round"
              strokeLinejoin="round"
              d="M3 3v1.5M3 21v-6m0 0l2.77-.693a9 9 0 016.208.682l.108.054a9 9 0 006.086.71l3.114-.779V4.5l-3.114.779a9 9 0 01-6.086-.71l-.108-.054a9 9 0 00-6.208-.682L3 4.5M3 15V4.5"
            />
          </svg>
          <span>{buttonText}</span>
        </button>
      )}

      {variant === 'button' && (
        <Button
          type="button"
          variant={buttonVariant}
          size={buttonSize}
          onClick={handleOpen}
          className={className}
        >
          <svg
            className="w-3.5 h-3.5 shrink-0 mr-1"
            fill="none"
            viewBox="0 0 24 24"
            stroke="currentColor"
            strokeWidth={2}
          >
            <path
              strokeLinecap="round"
              strokeLinejoin="round"
              d="M3 3v1.5M3 21v-6m0 0l2.77-.693a9 9 0 016.208.682l.108.054a9 9 0 006.086.71l3.114-.779V4.5l-3.114.779a9 9 0 01-6.086-.71l-.108-.054a9 9 0 00-6.208-.682L3 4.5M3 15V4.5"
            />
          </svg>
          <span>{buttonText}</span>
        </Button>
      )}

      {variant === 'icon' && (
        <button
          type="button"
          onClick={handleOpen}
          title={buttonText}
          aria-label={buttonText}
          className={`p-1 text-slate-400 hover:text-rose-600 hover:bg-rose-50 rounded-lg transition-colors cursor-pointer select-none ${className}`}
        >
          <svg
            className="w-4 h-4"
            fill="none"
            viewBox="0 0 24 24"
            stroke="currentColor"
            strokeWidth={2}
          >
            <path
              strokeLinecap="round"
              strokeLinejoin="round"
              d="M3 3v1.5M3 21v-6m0 0l2.77-.693a9 9 0 016.208.682l.108.054a9 9 0 006.086.71l3.114-.779V4.5l-3.114.779a9 9 0 01-6.086-.71l-.108-.054a9 9 0 00-6.208-.682L3 4.5M3 15V4.5"
            />
          </svg>
        </button>
      )}

      <ReportModal
        isOpen={isOpen}
        onClose={() => setIsOpen(false)}
        targetType={targetType}
        targetId={targetId}
        targetTitle={targetTitle}
        onSuccess={onSuccess}
        onSubmit={onSubmit}
      />
    </>
  );
}

export default ReportButton;
