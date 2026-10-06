import Link from 'next/link';
import Image from 'next/image';
import type { Listing } from '@/types';
import FavoriteButton from './FavoriteButton';
import { getImageUrl, isUnoptimizedImage } from '@/lib/images';
import { isListingAnObject } from '@/lib/categories';
import { Badge } from '@/components/ui/Badge';

interface ListingCardProps {
  data: Listing;
  // true for the cards above the fold: their cover is the page's Largest
  // Contentful Paint, which next/image otherwise reports in the console
  preload?: boolean;
}

// Map condition codes to human-readable labels and badge styles
const CONDITION_MAP: Record<string, { label: string; badgeClass: string }> = {
  NEW: {
    label: 'New',
    badgeClass: 'bg-emerald-50 text-emerald-700 border-emerald-200/60',
  },
  LIKE_NEW: {
    label: 'Like new',
    badgeClass: 'bg-cyan-50 text-cyan-800 border-cyan-200/60',
  },
  GOOD: {
    label: 'Good condition',
    badgeClass: 'bg-blue-50 text-blue-700 border-blue-200/60',
  },
  FAIR: {
    label: 'Fair condition',
    badgeClass: 'bg-amber-50 text-amber-700 border-amber-200/60',
  },
  FOR_PARTS: {
    label: 'For parts',
    badgeClass: 'bg-rose-50 text-rose-700 border-rose-200/60',
  },
};

export default function ListingCard({ data, preload = false }: ListingCardProps) {
  // Check if listing belongs to an object category
  const isObject = isListingAnObject(data);

  // Sold listings stay visible on the profile and in favorites, flag them
  const isSold = (data.status ?? '').toLowerCase() === 'sold';

  // Normalize condition code (only relevant for physical objects)
  const conditionKey = isObject && data.condition ? data.condition.toUpperCase().replace('-', '_') : null;
  const conditionInfo = conditionKey
    ? CONDITION_MAP[conditionKey] || {
        label: data.condition || 'Used',
        badgeClass: 'bg-slate-50 text-slate-700 border-slate-200/60',
      }
    : null;

  // Format price with locale currency
  const formattedPrice = new Intl.NumberFormat('fr-FR', {
    style: 'currency',
    currency: data.currency || 'EUR',
    maximumFractionDigits: 0,
  }).format(data.price);

  // Format published or creation date
  const formattedDate = data.published_at || data.created_at
    ? new Date(data.published_at || data.created_at).toLocaleDateString('fr-FR', {
        day: 'numeric',
        month: 'short',
      })
    : null;

  // Resolve image url with fallback and placeholder support
  const imageSource = data.cover_image?.storage_path || data.cover_image_id;
  const imageUrl = getImageUrl(imageSource, data.category_id);

  const categoryName = data.category?.category_name || null;
  const locationLabel = data.location?.location || '42 Campus';
  const sellerName = data.seller?.display_name || '42 Student';
  const sellerAvatar = data.seller?.avatar_path;
  const sellerRating = data.seller?.rating;
  const sellerRatingCount = data.seller?.rating_count ?? 0;

  return (
    <Link
      href={`/listings/${data.public_id}`}
      prefetch={false}
      className="card-premium group relative flex flex-col h-full rounded-2xl overflow-hidden bg-white text-slate-900 no-underline"
    >
      {/* Cover Image & Overlays */}
      <div className="relative aspect-[4/3] w-full overflow-hidden bg-slate-100">
        <Image
          src={imageUrl}
          alt={data.title}
          fill
          preload={preload}
          unoptimized={isUnoptimizedImage(imageUrl)}
          sizes="(max-width: 640px) 100vw, (max-width: 1024px) 50vw, 33vw"
          className="object-cover transition-transform duration-500 ease-out group-hover:scale-105"
        />

        {/* Gradient shadow overlay for badge readability */}
        <div className="absolute inset-0 bg-gradient-to-t from-black/40 via-transparent to-black/20 pointer-events-none" />

        {/* Category tag (top left) */}
        {categoryName && (
          <div className="absolute top-3 left-3">
            <span className="glass px-2.5 py-1 rounded-full text-xs font-semibold text-slate-900 tracking-tight shadow-xs">
              {categoryName}
            </span>
          </div>
        )}

        {/* Favorites button (top right) */}
        <div className="absolute top-3 right-3 z-10">
          <FavoriteButton
            listingId={data.public_id || data.id}
            initialFavorited={data.is_favorited}
            initialCount={data.favorites_count}
          />
        </div>

        {/* Condition badge (bottom left) - only for physical objects */}
        {isObject && conditionInfo && (
          <div className="absolute bottom-3 left-3">
            <span
              className={`inline-flex items-center px-2 py-0.5 rounded-md text-[11px] font-semibold border backdrop-blur-xs ${conditionInfo.badgeClass}`}
            >
              {conditionInfo.label}
            </span>
          </div>
        )}

        {/* Sold badge (bottom right) */}
        {isSold && (
          <span className="absolute bottom-3 right-3 z-20 rounded-md bg-rose-600 px-2 py-0.5 text-[11px] font-bold uppercase tracking-wide text-white shadow-sm">
            Vendu
          </span>
        )}
      </div>

      {/* Content Area */}
      <div
        className="flex flex-col flex-1 p-4 sm:p-5">
        {/* Title */}
        <h3 className="font-bold text-slate-900 text-base leading-snug line-clamp-1 group-hover:text-[#00babc] transition-colors">
          {data.title}
        </h3>

        {/* Short description preview */}
        <p className="text-xs text-slate-500 line-clamp-2 mt-1.5 mb-3 leading-relaxed">
          {data.body}
        </p>

        {/* Metadata row: Location & Published Date */}
        <div className="mt-auto flex items-center justify-between text-xs text-slate-500 pt-2 border-t border-slate-100">
          <div className="flex items-center gap-1.5 truncate max-w-[65%]">
            <svg
              className="w-3.5 h-3.5 text-slate-400 shrink-0"
              fill="none"
              viewBox="0 0 24 24"
              stroke="currentColor"
              strokeWidth={2}
            >
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                d="M15 10.5a3 3 0 11-6 0 3 3 0 016 0z"
              />
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                d="M19.5 10.5c0 7.142-7.5 11.25-7.5 11.25S4.5 17.642 4.5 10.5a7.5 7.5 0 1115 0z"
              />
            </svg>
            <span className="truncate">{locationLabel}</span>
          </div>

          {formattedDate && (
            <span className="shrink-0 text-slate-400 text-[11px]">
              {formattedDate}
            </span>
          )}
        </div>

        {/* Footer: Price & Seller */}
        <div className="flex items-center justify-between mt-3 pt-3 border-t border-slate-100">
          {/* Price */}
          <span className="text-lg sm:text-xl font-black text-slate-900 tracking-tight">
            {formattedPrice}
          </span>

          {/* Seller preview */}
          <div className="flex items-center gap-2">
            <div className="relative w-6 h-6 rounded-full overflow-hidden bg-slate-200 shrink-0 ring-1 ring-slate-200">
              {sellerAvatar ? (
                <Image
                  src={sellerAvatar}
                  alt={sellerName}
                  fill
                  sizes="24px"
                  className="object-cover"
                  unoptimized={isUnoptimizedImage(sellerAvatar)}
                />
              ) : (
                <div className="w-full h-full flex items-center justify-center text-[10px] font-bold text-slate-600 bg-slate-100">
                  {sellerName.charAt(0).toUpperCase()}
                </div>
              )}
            </div>
            <div className="flex flex-col text-right items-center">
              <span className="text-xs pb-0.5 font-medium text-slate-700 max-w-[90px] truncate leading-tight">
                {sellerName}
              </span>
              {sellerRatingCount === 0 ? (
                <Badge variant="default" className="text-[10px] px-1.5 py-0 font-medium">
                  Nouveau
                </Badge>
              ) : (
                <span className="text-[10px] text-amber-600 font-semibold flex items-center justify-end gap-0.5 leading-none mt-0.5">
                  ★ {sellerRating != null ? sellerRating.toFixed(1) : '0.0'}
                </span>
              )}
            </div>
          </div>
        </div>
      </div>
    </Link>
  );
}