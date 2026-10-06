import Link from 'next/link';
import Image from 'next/image';
import { notFound } from 'next/navigation';
import type { Metadata } from 'next';
import FavoriteButton from '@/components/listings/FavoriteButton';
import { ReportButton } from '@/components/ui/ReportButton';
import { listingsApi } from '@/lib/api/listings';
import { getImageUrl, isUnoptimizedImage } from '@/lib/images';
import { isListingAnObject } from '@/lib/categories';
import { DeleteListingButton } from '@/components/listings/DeleteListingButton';
import { ContactSellerButton } from '@/components/listings/ContactSellerButton';
import { MarkSoldListingButton } from '@/components/listings/MarkSoldListingButton';
import { SellerProfileLink } from '@/components/listings/SellerProfileLink';
import { Badge } from '@/components/ui/Badge';

interface PageProps {
  params: Promise<{
    public_id: string;
  }>;
}

// Generate dynamic metadata for SEO and social sharing
export async function generateMetadata(props: PageProps): Promise<Metadata> {
  const { public_id } = await props.params;
  const listing = await listingsApi.getByPublicId(public_id);

  if (!listing) {
    return {
      title: 'Annonce non trouvée | LeBon42',
    };
  }

  return {
    title: `${listing.title} | LeBon42`,
    description: listing.body?.slice(0, 160) || `${listing.title} — annonce LeBon42`,
  };
}

// Map condition codes to human-readable labels and badge styles
const CONDITION_CONFIG: Record<string, { label: string; badgeClass: string }> = {
  NEW: {
    label: 'Neuf (jamais utilisé)',
    badgeClass: 'bg-emerald-50 text-emerald-800 border-emerald-200/80',
  },
  LIKE_NEW: {
    label: 'Très bon état (comme neuf)',
    badgeClass: 'bg-cyan-50 text-cyan-800 border-cyan-200/80',
  },
  GOOD: {
    label: 'Bon état',
    badgeClass: 'bg-blue-50 text-blue-800 border-blue-200/80',
  },
  FAIR: {
    label: 'État correct',
    badgeClass: 'bg-amber-50 text-amber-800 border-amber-200/80',
  },
  FOR_PARTS: {
    label: 'Pour pièces / Réparation',
    badgeClass: 'bg-rose-50 text-rose-800 border-rose-200/80',
  },
};

export default async function ListingDetailPage(props: PageProps) {
  const { public_id } = await props.params;
  const listing = await listingsApi.getByPublicId(public_id);

  if (!listing) {
    notFound();
  }

  // Check if listing belongs to an object category
  const isObject = isListingAnObject(listing);

  // Normalize condition code (only relevant for physical objects)
  const conditionKey = isObject && listing.condition ? listing.condition.toUpperCase().replace('-', '_') : null;
  const conditionInfo = conditionKey
    ? CONDITION_CONFIG[conditionKey] || {
      label: listing.condition || 'Occasion',
      badgeClass: 'bg-slate-50 text-slate-700 border-slate-200',
    }
    : null;

  // Format price
  const formattedPrice = new Intl.NumberFormat('fr-FR', {
    style: 'currency',
    currency: listing.currency || 'EUR',
    maximumFractionDigits: 0,
  }).format(listing.price);

  // Format date
  const formattedDate = listing.published_at || listing.created_at
    ? new Date(listing.published_at || listing.created_at).toLocaleDateString('fr-FR', {
      day: 'numeric',
      month: 'long',
      year: 'numeric',
    })
    : null;

  const imageSource = listing.cover_image?.storage_path || listing.cover_image_id;
  const imageUrl = getImageUrl(imageSource, listing.category_id);

  const seller = listing.seller;
  const locationLabel = listing.location?.location || '42 Campus (Paris)';
  const categoryName = listing.category?.category_name || 'Divers';

  return (
    <main className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8 sm:py-10">
      {/* Breadcrumb & Navigation Bar */}
      <nav className="mb-6 flex flex-wrap items-center justify-between gap-4 text-xs sm:text-sm text-slate-500">
        <div className="flex items-center gap-2">
          <Link
            href="/"
            className="inline-flex items-center gap-1 font-medium text-slate-600 hover:text-[#00babc] transition-colors"
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
                d="M10.5 19.5L3 12m0 0l7.5-7.5M3 12h18"
              />
            </svg>
            <span>Retour aux annonces</span>
          </Link>
          <span className="text-slate-300">/</span>
          <span className="text-slate-600">{categoryName}</span>
          <span className="text-slate-300 hidden sm:inline">/</span>
          <span className="text-slate-400 truncate max-w-[200px] hidden sm:inline">
            {listing.title}
          </span>
        </div>
      </nav>

      {/* Main Grid Layout */}
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-8 lg:gap-10 items-start">
        {/* Left Column: Visuals & Specifications */}
        <div className="lg:col-span-7 xl:col-span-8 space-y-8">
          {/* Main Cover Image Display */}
          <div className="relative aspect-[16/10] w-full rounded-2xl overflow-hidden bg-slate-900 border border-slate-200/80 shadow-md">
            <Image
              src={imageUrl}
              alt={listing.title}
              fill
              priority
              unoptimized={isUnoptimizedImage(imageUrl)}
              sizes="(max-width: 1024px) 100vw, 65vw"
              className="object-cover"
            />

            {/* Gradient shadow for contrast */}
            <div className="absolute inset-0 bg-gradient-to-t from-black/50 via-transparent to-black/20 pointer-events-none" />

            {/* Category tag overlay */}
            <div className="absolute top-4 left-4">
              <span className="glass px-3 py-1 rounded-full text-xs font-bold text-slate-900 shadow-xs tracking-tight">
                {categoryName}
              </span>
            </div>

            {/* Favorites button overlay */}
            <div className="absolute top-4 right-4 z-10">
              <FavoriteButton
                listingId={listing.public_id || listing.id}
                initialFavorited={listing.is_favorited}
                initialCount={listing.favorites_count}
                className="px-3 py-1.5 text-xs"
              />
            </div>

            {/* Condition pill overlay (only for physical objects) */}
            {isObject && conditionInfo && (
              <div className="absolute bottom-4 left-4">
                <span
                  className={`inline-flex items-center px-3 py-1 rounded-lg text-xs font-bold border backdrop-blur-md ${conditionInfo.badgeClass}`}
                >
                  {conditionInfo.label}
                </span>
              </div>
            )}
          </div>

          {/* Description Section */}
          <section className="bg-white rounded-2xl p-6 sm:p-8 border border-slate-200/80 shadow-xs">
            <h2 className="text-xl font-bold text-slate-900 mb-4 tracking-tight">
              Description de l&apos;annonce
            </h2>
            <div className="text-slate-700 leading-relaxed text-sm sm:text-base whitespace-pre-line">
              {listing.body || "Aucune description fournie."}
            </div>
          </section>
        </div>

        {/* Right Column: Sticky Pricing, Actions & Seller Profile */}
        <aside className="lg:col-span-5 xl:col-span-4 lg:sticky lg:top-24 space-y-6">
          {/* Main Action & Price Box */}
          <div className="card-premium rounded-2xl p-6 sm:p-7 space-y-6 bg-white">
            {/* Title & Price Header */}
            <div>
              <span className="text-xs font-semibold text-[#009698] uppercase tracking-wider">
                {categoryName}
              </span>
              {listing.status === 'sold' && (
                <span className="ml-2 inline-flex items-center align-middle px-2 py-0.5 rounded-md bg-rose-600 text-white text-[11px] font-bold uppercase tracking-wide">
                  Vendu
                </span>
              )}
              <h1 className="text-2xl sm:text-3xl font-black text-slate-900 mt-1 tracking-tight">
                {listing.title}
              </h1>
              <div className="mt-4 flex items-baseline justify-between">
                <span className="text-3xl sm:text-4xl font-black text-slate-950 tracking-tight">
                  {formattedPrice}
                </span>
                {isObject && conditionInfo && (
                  <span
                    className={`text-xs px-2.5 py-1 rounded-md font-semibold border ${conditionInfo.badgeClass}`}
                  >
                    {conditionInfo.label}
                  </span>
                )}
              </div>
            </div>

            {/* Quick Metadata: Location & Date */}
            <div className="space-y-2.5 pt-4 border-t border-slate-100 text-xs sm:text-sm text-slate-600">
              <div className="flex items-center gap-2">
                <svg
                  className="w-4 h-4 text-slate-400 shrink-0"
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
                <span className="font-medium text-slate-900">{locationLabel}</span>
              </div>

              {formattedDate && (
                <div className="flex items-center gap-2">
                  <svg
                    className="w-4 h-4 text-slate-400 shrink-0"
                    fill="none"
                    viewBox="0 0 24 24"
                    stroke="currentColor"
                    strokeWidth={2}
                  >
                    <path
                      strokeLinecap="round"
                      strokeLinejoin="round"
                      d="M6.75 3v2.25M17.25 3v2.25M3 18.75V7.5a2.25 2.25 0 012.25-2.25h13.5A2.25 2.25 0 0121 7.5v11.25m-18 0A2.25 2.25 0 005.25 21h13.5A2.25 2.25 0 0021 18.75m-18 0v-7.5A2.25 2.25 0 015.25 9h13.5A2.25 2.25 0 0121 11.25v7.5"
                    />
                  </svg>
                  <span>Publiée le {formattedDate}</span>
                </div>
              )}
            </div>

            {/* Action Buttons */}
            <div className="space-y-3 pt-2">
              <ContactSellerButton
                listingPublicId={listing.public_id || listing.id}
                sellerId={seller?.id}
                sellerPublicId={seller?.public_id}
              />

              <FavoriteButton
                listingId={listing.public_id || listing.id}
                variant="button"
                initialFavorited={listing.is_favorited}
                initialCount={listing.favorites_count}
              />

              <MarkSoldListingButton
                listingId={listing.public_id || listing.id}
                sellerId={seller?.id}
                sellerPublicId={seller?.public_id}
                status={listing.status}
              />

              {seller && (
                <DeleteListingButton
                  listingId={listing.public_id || listing.id}
                  sellerId={seller.id}
                  sellerPublicId={seller.public_id}
                />
              )}
            </div>
          </div>

          {/* Seller Profile Card */}
          {seller && (
            <div className="card-premium rounded-2xl p-6 bg-white space-y-4">
              <h3 className="text-xs font-bold uppercase tracking-wider text-slate-400">
                À propos du vendeur
              </h3>

              <div className="flex items-center gap-3.5">
                <div className="relative w-14 h-14 rounded-full overflow-hidden bg-slate-200 shrink-0 ring-2 ring-[#00babc]/30">
                  {seller.avatar_path ? (
                    <Image
                      src={seller.avatar_path}
                      alt={seller.display_name}
                      fill
                      sizes="56px"
                      className="object-cover"
                      unoptimized={isUnoptimizedImage(seller.avatar_path)}
                    />
                  ) : (
                    <div className="w-full h-full flex items-center justify-center text-lg font-bold text-slate-600 bg-slate-100">
                      {seller.display_name.charAt(0).toUpperCase()}
                    </div>
                  )}
                </div>

                <div className="flex flex-col min-w-0">
                  <div className="flex items-center gap-1.5">
                    <span className="font-bold text-slate-900 text-base truncate">
                      {seller.display_name}
                    </span>
                  </div>

                  {(seller.rating_count ?? 0) === 0 ? (
                    <div className="mt-0.5">
                      <Badge variant="default" className="text-xs px-2 py-0.5 font-medium">
                        Nouveau
                      </Badge>
                    </div>
                  ) : (
                    <div className="flex items-center gap-1 text-xs text-slate-500 mt-0.5">
                      <span className="text-amber-500 font-bold">
                        ★ {seller.rating != null ? seller.rating.toFixed(1) : '0.0'}
                      </span>
                      <span>•</span>
                      <span>{seller.rating_count} avis</span>
                    </div>
                  )}
                </div>
              </div>

              {seller.bio && (
                <p className="text-xs text-slate-600 leading-relaxed italic pt-1">
                  &ldquo;{seller.bio}&rdquo;
                </p>
              )}

              <div className="pt-2 border-t border-slate-100">
                <SellerProfileLink
                  sellerPublicId={seller.public_id}
                  sellerId={seller.id}
                />
              </div>
            </div>
          )}

          {/* Moderation / Report Button */}
          <div className="text-center">
            <ReportButton
              targetType="listing"
              targetId={listing.public_id}
              targetTitle={listing.title}
              label="Signaler cette annonce"
            />
          </div>
        </aside>
      </div>
    </main>
  );
}
