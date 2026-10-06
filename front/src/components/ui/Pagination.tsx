'use client';

import React from 'react';
import Link from 'next/link';

export interface PaginationProps {
  currentPage: number;
  totalPages: number;
  totalResults: number;
  limit?: number;
  baseParams?: Record<string, string | number | undefined>;
  className?: string;
  onPageChange?: (page: number) => void;
  isLoading?: boolean;
}

// build the page numbers to show
function getPaginationRange(currentPage: number, totalPages: number): (number | 'ellipsis')[] {
  if (totalPages <= 7) {
    return Array.from({ length: totalPages }, (_, i) => i + 1);
  }

  // Near the start
  if (currentPage <= 4) {
    return [1, 2, 3, 4, 5, 'ellipsis', totalPages];
  }

  // Near the end
  if (currentPage >= totalPages - 3) {
    return [
      1,
      'ellipsis',
      totalPages - 4,
      totalPages - 3,
      totalPages - 2,
      totalPages - 1,
      totalPages,
    ];
  }

  // In the middle
  return [
    1,
    'ellipsis',
    currentPage - 1,
    currentPage,
    currentPage + 1,
    'ellipsis',
    totalPages,
  ];
}

const NAV_CONTROL =
  'inline-flex items-center gap-1 px-3 py-2 text-xs sm:text-sm font-semibold rounded-xl border border-slate-200 bg-white hover:border-slate-300 hover:bg-slate-50 text-slate-700 transition-all select-none active:scale-[0.98]';
const NAV_DISABLED =
  'inline-flex items-center gap-1 px-3 py-2 text-xs sm:text-sm font-semibold rounded-xl border border-slate-200 text-slate-400 bg-slate-50/50 opacity-60 cursor-not-allowed select-none';
const PAGE_CONTROL =
  'w-8 h-9 sm:w-10 sm:h-10 rounded-xl border border-slate-200 bg-white hover:border-slate-300 hover:bg-slate-50 text-slate-700 font-semibold flex items-center justify-center transition-all text-xs sm:text-sm select-none active:scale-[0.98]';

export function Pagination({
  currentPage,
  totalPages,
  totalResults,
  limit = 30,
  baseParams = {},
  className = '',
  onPageChange,
  isLoading = false,
}: PaginationProps) {
  if (totalPages <= 1 && totalResults <= limit) {
    return null;
  }

  const buildUrl = (pageNumber: number): string => {
    const params = new URLSearchParams();

    Object.entries(baseParams).forEach(([key, value]) => {
      if (value !== undefined && value !== null && value !== '' && key !== 'page') {
        params.set(key, String(value));
      }
    });

    if (pageNumber > 1) {
      params.set('page', String(pageNumber));
    } else if (pageNumber === 1 && Object.keys(baseParams).some(k => k !== 'page' && baseParams[k])) {
      params.set('page', '1');
    }

    const qs = params.toString();
    return qs ? `/?${qs}` : '/';
  };

  const startItem = totalResults === 0 ? 0 : (currentPage - 1) * limit + 1;
  const endItem = Math.min(currentPage * limit, totalResults);
  const pages = getPaginationRange(currentPage, totalPages);
  const isFirstPage = currentPage <= 1;
  const isLastPage = currentPage >= totalPages;

  // prev/next: link normally, button in client mode
  const renderNavControl = (
    page: number,
    ariaLabel: string,
    disabled: boolean,
    children: React.ReactNode
  ): React.ReactNode => {
    if (disabled || isLoading) {
      return (
        <span aria-disabled="true" className={NAV_DISABLED}>
          {children}
        </span>
      );
    }
    if (onPageChange) {
      return (
        <button type="button" onClick={() => onPageChange(page)} aria-label={ariaLabel} className={NAV_CONTROL}>
          {children}
        </button>
      );
    }
    return (
      <Link href={buildUrl(page)} aria-label={ariaLabel} className={NAV_CONTROL}>
        {children}
      </Link>
    );
  };

  return (
    <nav
      role="navigation"
      aria-label="Pagination des annonces"
      aria-busy={isLoading}
      className={`flex flex-col sm:flex-row items-center justify-between gap-4 pt-6 border-t border-slate-200 ${isLoading ? 'opacity-60' : ''} ${className}`}
    >
      {/* Summary indicator */}
      <div className="text-xs sm:text-sm text-slate-500 order-2 sm:order-1">
        Affichage de <span className="font-semibold text-slate-900">{startItem}</span> à{' '}
        <span className="font-semibold text-slate-900">{endItem}</span> sur{' '}
        <span className="font-semibold text-slate-900">{totalResults}</span>{' '}
        {totalResults <= 1 ? 'annonce' : 'annonces'}
      </div>

      {/* Navigation and page links */}
      <div className="flex items-center gap-1.5 sm:gap-2 order-1 sm:order-2">
        {/* Previous page button */}
        {renderNavControl(
          currentPage - 1,
          "Page précédente",
          isFirstPage,
          <>
            <svg
              className="w-4 h-4"
              fill="none"
              stroke="currentColor"
              viewBox="0 0 24 24"
              strokeWidth={2}
            >
              <path strokeLinecap="round" strokeLinejoin="round" d="M15.75 19.5L8.25 12l7.5-7.5" />
            </svg>
            <span className="hidden sm:inline">Précédent</span>
          </>
        )}

        {/* Page numbers */}
        <div className="flex items-center gap-1">
          {pages.map((item, index) => {
            if (item === 'ellipsis') {
              return (
                <span
                  key={`ellipsis-${index}`}
                  className="w-8 h-9 sm:w-10 sm:h-10 flex items-center justify-center text-slate-400 font-medium select-none text-xs sm:text-sm"
                >
                  ...
                </span>
              );
            }

            const isCurrent = item === currentPage;

            if (isCurrent) {
              return (
                <span
                  key={item}
                  aria-current="page"
                  className="w-8 h-9 sm:w-10 sm:h-10 rounded-xl bg-[#00babc] text-slate-950 font-bold flex items-center justify-center shadow-xs text-xs sm:text-sm select-none"
                >
                  {item}
                </span>
              );
            }

            if (onPageChange) {
              return (
                <button
                  key={item}
                  type="button"
                  disabled={isLoading}
                  onClick={() => onPageChange(item)}
                  aria-label={`Aller à la page ${item}`}
                  className={PAGE_CONTROL}
                >
                  {item}
                </button>
              );
            }

            return (
              <Link
                key={item}
                href={buildUrl(item)}
                aria-label={`Aller à la page ${item}`}
                className={PAGE_CONTROL}
              >
                {item}
              </Link>
            );
          })}
        </div>

        {/* Next page button */}
        {renderNavControl(
          currentPage + 1,
          "Page suivante",
          isLastPage,
          <>
            <span className="hidden sm:inline">Suivant</span>
            <svg
              className="w-4 h-4"
              fill="none"
              stroke="currentColor"
              viewBox="0 0 24 24"
              strokeWidth={2}
            >
              <path strokeLinecap="round" strokeLinejoin="round" d="M8.25 4.5l7.5 7.5-7.5 7.5" />
            </svg>
          </>
        )}
      </div>
    </nav>
  );
}

export default Pagination;
