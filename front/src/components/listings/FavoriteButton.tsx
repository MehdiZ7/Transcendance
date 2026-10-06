'use client';

import React, { useState, useEffect } from 'react';
import { useRouter } from 'next/navigation';
import { listingsApi } from '@/lib/api/listings';
import { Button } from '@/components/ui/Button';
import { useCurrentUser } from '@/hooks/useCurrentUser';
import { useAuthModal } from '@/context/AuthModalContext';
import { logError } from '@/lib/log';

export interface FavoriteButtonProps {
  listingId?: string;
  initialFavorited?: boolean;
  initialCount?: number;
  variant?: 'badge' | 'button';
  className?: string;
  onToggle?: (isFavorited: boolean, newCount: number) => void;
}

export function FavoriteButton({
  listingId,
  initialFavorited = false,
  initialCount = 0,
  variant = 'badge',
  className = '',
  onToggle,
}: FavoriteButtonProps) {
  const router = useRouter();
  const { user } = useCurrentUser();
  const { openAuthModal } = useAuthModal();
  const [isFavorited, setIsFavorited] = useState(Boolean(initialFavorited));
  const [count, setCount] = useState(initialCount);
  const [isLoading, setIsLoading] = useState(false);

  // Sync local state when the server-provided props change (e.g. after router.refresh()).
  const [prevInitialFavorited, setPrevInitialFavorited] = useState(initialFavorited);
  if (initialFavorited !== prevInitialFavorited) {
    setPrevInitialFavorited(initialFavorited);
    setIsFavorited(Boolean(initialFavorited));
  }

  const [prevInitialCount, setPrevInitialCount] = useState(initialCount);
  if (initialCount !== prevInitialCount) {
    setPrevInitialCount(initialCount);
    setCount(initialCount);
  }

  // Sync every favorite button of the same listing on the page
  useEffect(() => {
    if (!listingId) return;

    const handleSync = (e: Event) => {
      const customEvent = e as CustomEvent<{ listingId: string; isFavorited: boolean; count: number }>;
      if (customEvent.detail?.listingId === listingId) {
        setIsFavorited(customEvent.detail.isFavorited);
        setCount(customEvent.detail.count);
      }
    };

    window.addEventListener('favorite-updated', handleSync);
    return () => {
      window.removeEventListener('favorite-updated', handleSync);
    };
  }, [listingId]);

  // Toggle favorite state with click event isolation
  const handleToggle = async (e: React.MouseEvent<HTMLButtonElement>) => {
    e.preventDefault();
    e.stopPropagation();

    if (!user) {
      openAuthModal();
      return;
    }

    if (isLoading) return;

    const nextState = !isFavorited;
    const nextCount = nextState ? count + 1 : Math.max(0, count - 1);

    // Immediate optimistic update
    setIsFavorited(nextState);
    setCount(nextCount);
    onToggle?.(nextState, nextCount);

    if (listingId && typeof window !== 'undefined') {
      window.dispatchEvent(
        new CustomEvent('favorite-updated', {
          detail: { listingId, isFavorited: nextState, count: nextCount },
        })
      );
    }

    if (listingId) {
      setIsLoading(true);
      try {
        if (nextState) {
          await listingsApi.addFavorite(listingId);
        } else {
          await listingsApi.removeFavorite(listingId);
        }
        // Refresh the page's components and Server Components
        router.refresh();
      } catch (error) {
        logError('Erreur lors de la mise à jour des favoris :', error);
        // On error, roll back to the previous state
        setIsFavorited(!nextState);
        setCount(count);
        onToggle?.(!nextState, count);
        if (typeof window !== 'undefined') {
          window.dispatchEvent(
            new CustomEvent('favorite-updated', {
              detail: { listingId, isFavorited: !nextState, count },
            })
          );
        }
      } finally {
        setIsLoading(false);
      }
    }
  };

  // Full-width action button variant (used on listing detail page)
  if (variant === 'button') {
    return (
      <Button
        type="button"
        variant="outline"
        size="lg"
        fullWidth
        onClick={handleToggle}
        disabled={isLoading}
        aria-label={isFavorited ? 'Retirer des favoris' : 'Ajouter aux favoris'}
        className={`${
          isFavorited
            ? 'border-rose-200 bg-rose-50 text-rose-600 hover:bg-rose-100/70 hover:text-rose-700 shadow-xs'
            : 'border-slate-200 hover:border-rose-300 hover:bg-rose-50/50 text-slate-700 hover:text-rose-600'
        } ${className}`}
      >
        <svg
          className={`w-4 h-4 transition-transform duration-200 ${
            isFavorited
              ? 'fill-rose-500 text-rose-500 scale-110'
              : 'fill-none stroke-current hover:scale-110'
          }`}
          viewBox="0 0 24 24"
          strokeWidth={2}
        >
          <path
            strokeLinecap="round"
            strokeLinejoin="round"
            d="M21 8.25c0-2.485-2.099-4.5-4.688-4.5-1.935 0-3.597 1.126-4.312 2.733-.715-1.607-2.377-2.733-4.313-2.733C5.1 3.75 3 5.765 3 8.25c0 7.22 9 12 9 12s9-4.78 9-12z"
          />
        </svg>
        <span>{isFavorited ? 'Dans vos favoris' : 'Ajouter aux favoris'}</span>
      </Button>
    );
  }

  // Floating badge variant (used on listing cards and cover overlays)
  return (
    <button
      type="button"
      onClick={handleToggle}
      disabled={isLoading}
      aria-label={isFavorited ? 'Retirer des favoris' : 'Ajouter aux favoris'}
      className={`group/like flex items-center gap-1.5 glass px-2.5 py-1 rounded-full text-xs font-semibold shadow-xs cursor-pointer select-none transition-all duration-200 hover:scale-105 active:scale-90 hover:bg-white/90 ${
        isFavorited
          ? 'text-rose-600 bg-white/90 shadow-rose-500/10'
          : 'text-slate-800 hover:text-rose-500'
      } ${isLoading ? 'opacity-70 cursor-wait' : ''} ${className}`}
    >
      <svg
        className={`w-3.5 h-3.5 transition-transform duration-200 ${
          isFavorited
            ? 'fill-rose-500 text-rose-500 scale-110'
            : 'fill-none stroke-current group-hover/like:text-rose-500 group-hover/like:scale-110'
        }`}
        viewBox="0 0 24 24"
        strokeWidth={2}
      >
        <path
          strokeLinecap="round"
          strokeLinejoin="round"
          d="M21 8.25c0-2.485-2.099-4.5-4.688-4.5-1.935 0-3.597 1.126-4.312 2.733-.715-1.607-2.377-2.733-4.313-2.733C5.1 3.75 3 5.765 3 8.25c0 7.22 9 12 9 12s9-4.78 9-12z"
        />
      </svg>
      <span className="tabular-nums transition-colors">{count}</span>
    </button>
  );
}

export default FavoriteButton;
