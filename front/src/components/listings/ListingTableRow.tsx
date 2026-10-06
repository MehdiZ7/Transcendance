'use client';

import Link from 'next/link';
import Image from 'next/image';
import type { TopLikedListingItem } from '@/types';
import { getImageUrl, isUnoptimizedImage } from '@/lib/images';
import { Badge } from '@/components/ui/Badge';

export interface ListingTableRowProps {
  listing: TopLikedListingItem;
  rank?: number;
  className?: string;
}

export function ListingTableRowSkeleton() {
  return (
    <tr className="border-b border-slate-100 animate-pulse">
      <td className="py-4 pl-4 pr-3 sm:pl-6 text-sm">
        <div className="h-7 w-7 rounded-full bg-slate-200 mx-auto" />
      </td>
      <td className="py-4 px-3 text-sm">
        <div className="flex items-center gap-3">
          <div className="h-12 w-12 rounded-xl bg-slate-200 shrink-0" />
          <div className="space-y-1.5 min-w-0 flex-1">
            <div className="h-4 w-40 bg-slate-200 rounded" />
            <div className="h-3 w-24 bg-slate-100 rounded" />
          </div>
        </div>
      </td>
      <td className="py-4 px-3 text-sm hidden md:table-cell">
        <div className="h-5 w-20 bg-slate-200 rounded-full" />
      </td>
      <td className="py-4 px-3 text-sm">
        <div className="h-4 w-16 bg-slate-200 rounded" />
      </td>
      <td className="py-4 px-3 text-sm hidden sm:table-cell text-center">
        <div className="h-4 w-12 bg-slate-200 rounded mx-auto" />
      </td>
      <td className="py-4 px-3 text-sm text-center">
        <div className="h-5 w-14 bg-rose-100 rounded-full mx-auto" />
      </td>
      <td className="py-4 pl-3 pr-4 sm:pr-6 text-right">
        <div className="h-8 w-16 bg-slate-200 rounded-lg ml-auto" />
      </td>
    </tr>
  );
}

export function ListingTableRow({
  listing,
  rank,
  className = '',
}: ListingTableRowProps) {
  const currentRank = rank ?? listing.rank;

  // Format price
  const formattedPrice = new Intl.NumberFormat('fr-FR', {
    style: 'currency',
    currency: listing.currency || 'EUR',
    maximumFractionDigits: 0,
  }).format(listing.price);

  // Resolve thumbnail image
  const resolvedImageUrl = getImageUrl(listing.imageUrl);

  // Badge rank styling (Top 1 Gold, Top 2 Silver, Top 3 Bronze, others Neutral)
  const getRankBadge = (pos: number) => {
    if (pos === 1) {
      return (
        <span
          title="1ère place"
          className="inline-flex items-center justify-center h-7 w-7 rounded-full bg-amber-100 text-amber-800 border border-amber-300 font-bold text-xs shadow-xs"
        >
          🥇
        </span>
      );
    }
    if (pos === 2) {
      return (
        <span
          title="2ème place"
          className="inline-flex items-center justify-center h-7 w-7 rounded-full bg-slate-200 text-slate-700 border border-slate-300 font-bold text-xs shadow-xs"
        >
          🥈
        </span>
      );
    }
    if (pos === 3) {
      return (
        <span
          title="3ème place"
          className="inline-flex items-center justify-center h-7 w-7 rounded-full bg-orange-100 text-orange-800 border border-orange-300 font-bold text-xs shadow-xs"
        >
          🥉
        </span>
      );
    }
    return (
      <span className="inline-flex items-center justify-center h-7 w-7 rounded-full bg-slate-100 text-slate-600 border border-slate-200 font-semibold text-xs">
        #{pos}
      </span>
    );
  };

  return (
    <tr
      className={`group hover:bg-slate-50/80 transition-colors border-b border-slate-100 last:border-0 ${className}`}
    >
      {/* Rang */}
      <td className="py-4 pl-4 pr-3 sm:pl-6 text-sm text-center whitespace-nowrap">
        {getRankBadge(currentRank)}
      </td>

      {/* Listing (image + title + seller/campus) */}
      <td className="py-4 px-3 text-sm">
        <div className="flex items-center gap-3">
          <Link
            href={`/listings/${listing.public_id}`}
            className="relative h-12 w-12 rounded-xl overflow-hidden bg-slate-100 border border-slate-200/80 shrink-0 transition-all"
          >
            <Image
              src={resolvedImageUrl}
              alt={listing.title}
              fill
              sizes="64px"
              unoptimized={isUnoptimizedImage(resolvedImageUrl)}
              className="object-cover transition-transform duration-300"
            />
          </Link>
          <div className="min-w-0 flex-1">
            <Link
              href={`/listings/${listing.public_id}`}
              className="font-semibold text-slate-900 hover:text-cyan-600 transition-colors line-clamp-1 block"
              title={listing.title}
            >
              {listing.title}
            </Link>
            <div className="flex items-center gap-1.5 text-xs text-slate-500 mt-0.5">
              <span>{listing.sellerName}</span>
              <span>•</span>
              <span className="truncate">{listing.campusName}</span>
            </div>
          </div>
        </div>
      </td>

      {/* Category */}
      <td className="py-4 px-3 text-sm hidden md:table-cell whitespace-nowrap">
        <Badge variant="default" className="text-xs bg-slate-100 text-slate-700">
          {listing.categoryName}
        </Badge>
      </td>

      {/* Prix */}
      <td className="py-4 px-3 text-sm font-bold text-slate-900 whitespace-nowrap">
        {formattedPrice}
      </td>

      {/* Vues */}
      <td className="py-4 px-3 text-sm hidden sm:table-cell text-center whitespace-nowrap text-slate-600">
        <div className="inline-flex items-center gap-1">
          <svg
            className="w-4 h-4 text-slate-400"
            fill="none"
            viewBox="0 0 24 24"
            stroke="currentColor"
            strokeWidth={2}
          >
            <path
              strokeLinecap="round"
              strokeLinejoin="round"
              d="M15 12a3 3 0 11-6 0 3 3 0 016 0z"
            />
            <path
              strokeLinecap="round"
              strokeLinejoin="round"
              d="M2.458 12C3.732 7.943 7.523 5 12 5c4.478 0 8.268 2.943 9.542 7-1.274 4.057-5.064 7-9.542 7-4.477 0-8.268-2.943-9.542-7z"
            />
          </svg>
          <span className="tabular-nums font-medium">
            {listing.view_count.toLocaleString('fr-FR')}
          </span>
        </div>
      </td>

      {/* Favoris / Likes */}
      <td className="py-4 px-3 text-sm text-center whitespace-nowrap">
        <span className="inline-flex items-center gap-1 px-2.5 py-1 rounded-full text-xs font-semibold bg-rose-50 text-rose-700 border border-rose-200/60 shadow-xs">
          <svg
            className="w-3.5 h-3.5 fill-rose-500 text-rose-500"
            viewBox="0 0 24 24"
          >
            <path d="M12 21.35l-1.45-1.32C5.4 15.36 2 12.28 2 8.5 2 5.42 4.42 3 7.5 3c1.74 0 3.41.81 4.5 2.09C13.09 3.81 14.76 3 16.5 3 19.58 3 22 5.42 22 8.5c0 3.78-3.4 6.86-8.55 11.54L12 21.35z" />
          </svg>
          <span className="tabular-nums">
            {listing.favorites_count.toLocaleString('fr-FR')}
          </span>
        </span>
      </td>

      {/* Action / Lien */}
      <td className="py-4 pl-3 pr-4 sm:pr-6 text-sm text-right whitespace-nowrap">
        <Link
          href={`/listings/${listing.public_id}`}
          className="inline-flex items-center gap-1 text-xs font-semibold text-cyan-700 hover:text-cyan-800 bg-cyan-50 hover:bg-cyan-100/80 px-3 py-1.5 rounded-lg border border-cyan-200/60 transition-colors"
        >
          <span>Voir</span>
          <svg
            className="w-3.5 h-3.5"
            fill="none"
            viewBox="0 0 24 24"
            stroke="currentColor"
            strokeWidth={2}
          >
            <path
              strokeLinecap="round"
              strokeLinejoin="round"
              d="M9 5l7 7-7 7"
            />
          </svg>
        </Link>
      </td>
    </tr>
  );
}

export default ListingTableRow;
