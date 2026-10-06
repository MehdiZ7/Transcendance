import Link from 'next/link';
import Image from 'next/image';
import { Card } from '@/components/ui/Card';
import { Button } from '@/components/ui/Button';
import { Badge, type BadgeVariant } from '@/components/ui/Badge';
import { Avatar } from '@/components/ui/Avatar';
import type { Report, ReportStatus, ReportTargetType, Review } from '@/types/report';
import type { Listing } from '@/types/listing';
import type { Message } from '@/types/message';
import type { PublicUser, User } from '@/types/user';
import { getImageUrl, isUnoptimizedImage } from '@/lib/images';

export interface ReportCardProps {
  report: Report;
  onReject?: (report: Report) => void | Promise<void>;
  onDelete?: (report: Report) => void | Promise<void>;
  onBlockUser?: (report: Report) => void | Promise<void>;
  onReopen?: (report: Report) => void | Promise<void>;
  className?: string;
  isProcessing?: boolean;
}

// Helpers for normalized values
function normalizeTargetType(targetType: ReportTargetType): 'listing' | 'user' | 'message' | 'review' | 'other' {
  if (targetType === 'listing') return 'listing';
  if (targetType === 'user') return 'user';
  if (targetType === 'message') return 'message';
  if (targetType === 'review') return 'review';
  return 'other';
}

function normalizeStatus(status: ReportStatus): 'open' | 'in_progress' | 'resolved' | 'closed' {
  if (status === 'open') return 'open';
  if (status === 'in_progress') return 'in_progress';
  if (status === 'resolved') return 'resolved';
  if (status === 'closed') return 'closed';
  return 'open';
}

// Target type metadata (label, badge color)
const TARGET_TYPE_CONFIG: Record<
  string,
  { label: string; badgeVariant: BadgeVariant }
> = {
  listing: {
    label: 'Annonce',
    badgeVariant: 'default',
  },
  user: {
    label: 'Utilisateur',
    badgeVariant: 'moderator',
  },
  message: {
    label: 'Message',
    badgeVariant: 'admin',
  },
  review: {
    label: 'Avis',
    badgeVariant: 'warning',
  },
  other: {
    label: 'Entité',
    badgeVariant: 'default',
  },
};

// Status metadata
const STATUS_CONFIG: Record<
  'open' | 'in_progress' | 'resolved' | 'closed',
  { label: string; badgeVariant: BadgeVariant }
> = {
  open: {
    label: 'En attente',
    badgeVariant: 'warning',
  },
  in_progress: {
    label: 'En cours d’examen',
    badgeVariant: 'moderator',
  },
  resolved: {
    label: 'Résolu',
    badgeVariant: 'success',
  },
  closed: {
    label: 'Rejeté / Fermé',
    badgeVariant: 'closed',
  },
};

function formatReportDate(dateString: string): string {
  try {
    const date = new Date(dateString);
    if (isNaN(date.getTime())) return dateString;
    return new Intl.DateTimeFormat('fr-FR', {
      day: 'numeric',
      month: 'short',
      year: 'numeric',
      hour: '2-digit',
      minute: '2-digit',
    }).format(date);
  } catch {
    return dateString;
  }
}

export function ReportCard({
  report,
  onReject,
  onDelete,
  onBlockUser,
  onReopen,
  className = '',
  isProcessing = false,
}: ReportCardProps) {
  const normType = normalizeTargetType(report.target_type);
  const normStatus = normalizeStatus(report.status);

  const typeConfig = TARGET_TYPE_CONFIG[normType] || TARGET_TYPE_CONFIG.other;
  const statusConfig = STATUS_CONFIG[normStatus] || STATUS_CONFIG.open;

  const reporterName = report.reporter?.display_name || `Utilisateur #${report.reporter_id.slice(-6)}`;
  const reporterAvatar = report.reporter?.avatar_path;
  const formattedDate = formatReportDate(report.created_at);
  const isTreated = normStatus === 'resolved' || normStatus === 'closed' || Boolean(report.closed_at);
  const treatedDate = report.closed_at ? formatReportDate(report.closed_at) : null;

  // Render preview according to target type
  const renderTargetPreview = () => {
    if (!report.target) {
      return (
        <div className="flex items-center justify-between text-xs text-slate-500 bg-slate-50 border border-dashed border-slate-200 rounded-xl p-3">
          <span>
            Identifiant cible : <span className="font-mono text-slate-700">{report.target_id}</span>
          </span>
          <span className="text-[11px] text-slate-400 italic">Détails non chargés</span>
        </div>
      );
    }

    // 1. Listing Target
    if (normType === 'listing') {
      const listing = report.target as Listing;
      const cover = listing.cover_image?.storage_path || listing.cover_image_id;
      const imageUrl = cover ? getImageUrl(cover, listing.category_id) : null;
      const priceText =
        listing.price != null
          ? new Intl.NumberFormat('fr-FR', { style: 'currency', currency: listing.currency || 'EUR' }).format(
              listing.price
            )
          : null;

      return (
        <div className="flex flex-col sm:flex-row gap-3.5 bg-slate-50/80 border border-slate-200/80 rounded-xl p-3.5 transition-colors hover:bg-slate-50">
          {imageUrl && (
            <div className="relative w-full sm:w-24 h-24 sm:h-20 shrink-0 rounded-lg overflow-hidden bg-slate-200">
              <Image
                src={imageUrl}
                alt={listing.title || 'Annonce signalée'}
                fill
                sizes="(max-width: 640px) 100vw, 96px"
                unoptimized={isUnoptimizedImage(imageUrl)}
                className="object-cover"
              />
            </div>
          )}
          <div className="flex flex-col justify-between flex-1 min-w-0">
            <div>
              <div className="flex items-start justify-between gap-2">
                <p className="font-semibold text-sm text-slate-900 line-clamp-1">
                  {listing.title || `Annonce #${listing.id || report.target_id}`}
                </p>
                {priceText && <span className="text-sm font-bold text-slate-900 shrink-0">{priceText}</span>}
              </div>
              {listing.body && <p className="text-xs text-slate-600 line-clamp-2 mt-1">{listing.body}</p>}
            </div>

            <div className="flex items-center justify-between gap-2 mt-2 pt-2 border-t border-slate-200/60 text-[11px] text-slate-500">
              <span>Vendeur : {listing.seller?.display_name || 'Inconnu'}</span>
              {listing.public_id && (
                <Link
                  href={`/listings/${listing.public_id}`}
                  target="_blank"
                  className="text-[#00babc] hover:underline font-medium inline-flex items-center gap-1"
                >
                  Voir l’annonce ↗
                </Link>
              )}
            </div>
          </div>
        </div>
      );
    }

    // 2. User Target
    if (normType === 'user') {
      const targetUser = report.target as PublicUser | User;
      return (
        <div className="flex items-center justify-between gap-3 bg-slate-50/80 border border-slate-200/80 rounded-xl p-3.5">
          <div className="flex items-center gap-3 min-w-0">
            <Avatar
              src={targetUser.avatar_path}
              alt={targetUser.display_name || 'Utilisateur'}
              size="md"
            />
            <div className="min-w-0">
              <div className="flex items-center gap-2">
                <p className="font-semibold text-sm text-slate-900 truncate">
                  {targetUser.display_name || 'Utilisateur anonyme'}
                </p>
                <Badge variant="default" className="text-[10px] py-0 px-1.5">
                  {targetUser.role || 'user'}
                </Badge>
              </div>
              {targetUser.bio && (
                <p className="text-xs text-slate-500 truncate mt-0.5 max-w-sm">{targetUser.bio}</p>
              )}
              {targetUser.rating != null && (
                <p className="text-[11px] text-amber-600 font-medium mt-0.5">
                  ★ {targetUser.rating.toFixed(1)} ({targetUser.rating_count ?? 0} avis)
                </p>
              )}
            </div>
          </div>

          {targetUser.public_id && (
            <Link
              href={`/profile/${targetUser.public_id}`}
              target="_blank"
              className="text-xs font-semibold text-[#00babc] hover:underline shrink-0"
            >
              Profil ↗
            </Link>
          )}
        </div>
      );
    }

    // 3. Message Target
    if (normType === 'message') {
      const message = report.target as Message;
      return (
        <div className="bg-slate-50/80 border border-slate-200/80 rounded-xl p-3.5 space-y-2">
          <div className="flex items-center justify-between text-[11px] text-slate-500">
            <span className="font-medium text-slate-700">
              Expéditeur : {message.sender?.display_name || `ID #${message.sender_id?.slice(-6) || 'inconnu'}`}
            </span>
            {message.created_at && <span>{formatReportDate(message.created_at)}</span>}
          </div>
          <div className="bg-white border border-slate-200 rounded-lg p-3 text-xs text-slate-800 italic leading-relaxed">
            &ldquo;{message.body || 'Message vide'}&rdquo;
          </div>
        </div>
      );
    }

    // 4. Review Target
    if (normType === 'review') {
      const review = report.target as Review;
      return (
        <div className="bg-slate-50/80 border border-slate-200/80 rounded-xl p-3.5 space-y-2">
          <div className="flex items-center justify-between text-xs">
            <span className="font-semibold text-amber-600">
              ★ {review.rating}/5
            </span>
            <span className="text-[11px] text-slate-400">
              Auteur : {review.author?.display_name || `#${review.author_id.slice(-6)}`}
            </span>
          </div>
          <p className="text-xs text-slate-700 bg-white border border-slate-200 rounded-lg p-2.5">
            {review.body || 'Sans commentaire écrit'}
          </p>
        </div>
      );
    }

    return null;
  };

  return (
    <Card className={`relative h-full flex flex-col overflow-hidden transition-all duration-200 hover:shadow-md ${className}`}>
      {/* Top Header: Target Type, Status & ID */}
      <div className="flex flex-wrap items-center justify-between gap-2 pb-3.5 border-b border-slate-100 shrink-0">
        <div className="flex items-center gap-2">
          <Badge variant={typeConfig.badgeVariant} className="font-semibold">
            {typeConfig.label}
          </Badge>
          <span className="text-xs font-mono text-slate-400">
            #{report.id.slice(-8)}
          </span>
        </div>

        <div className="flex items-center gap-2">
          <Badge variant={statusConfig.badgeVariant}>
            {statusConfig.label}
          </Badge>
          <span className="text-xs text-slate-400 hidden sm:inline">
            {formattedDate}
          </span>
        </div>
      </div>

      {/* Main Body */}
      <div className="py-4 space-y-4 flex-1 flex flex-col justify-between">
        <div className="space-y-4">
          {/* Reporter Info Row */}
          <div className="flex items-center justify-between gap-3 text-xs">
            <div className="flex items-center gap-2.5">
              <Avatar
                src={reporterAvatar}
                alt={reporterName}
                size="sm"
              />
              <div>
                <span className="text-slate-400 text-[11px] block">Signalé par</span>
                <span className="font-medium text-slate-800">{reporterName}</span>
              </div>
            </div>
            <span className="text-slate-400 text-[11px] sm:hidden">
              {formattedDate}
            </span>
          </div>

          {/* Reason / Motif Box */}
          <div className="bg-amber-50/60 border border-amber-200/70 rounded-xl p-3">
            <div className="flex items-center gap-1.5 text-xs font-semibold text-amber-900 mb-1">
              <svg
                className="w-4 h-4 text-amber-600 shrink-0"
                fill="none"
                viewBox="0 0 24 24"
                stroke="currentColor"
                strokeWidth={2}
              >
                <path
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  d="M12 9v3.75m9-.75a9 9 0 11-18 0 9 9 0 0118 0zm-9 3.75h.008v.008H12v-.008z"
                />
              </svg>
              <span>Motif du signalement</span>
            </div>
            <p className="text-xs text-amber-950/90 leading-relaxed font-normal pl-5.5">
              {report.reason}
            </p>
          </div>
        </div>

        {/* Target Entity Preview */}
        <div className="space-y-1.5 pt-1">
          <div className="text-xs font-medium text-slate-700">
            <span>Contenu concerné ({typeConfig.label}) :</span>
          </div>
          {renderTargetPreview()}
        </div>
      </div>

      {/* Moderation Footer: Action Buttons or Resolution Status */}
      {(isTreated || onReject || onDelete || onBlockUser || onReopen) && (
        <div className="pt-3.5 border-t border-slate-100 mt-auto shrink-0 space-y-3">
          {isTreated && (
            <div className="flex items-center gap-1.5 text-xs text-slate-500">
              <svg
                className="w-4 h-4 text-emerald-600 shrink-0"
                fill="none"
                viewBox="0 0 24 24"
                stroke="currentColor"
                strokeWidth={2}
              >
                <path
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  d="M9 12.75L11.25 15 15 9.75M21 12a9 9 0 11-18 0 9 9 0 0118 0z"
                />
              </svg>
              <span>{treatedDate ? `Demande traitée le ${treatedDate}` : 'Demande traitée'}</span>
            </div>
          )}

          {isTreated && onReopen && (
            <Button
              variant="outline"
              size="sm"
              fullWidth
              isLoading={isProcessing}
              onClick={() => onReopen(report)}
              className="w-full text-xs sm:text-sm text-slate-700 hover:text-slate-900 justify-center py-2.5 bg-white"
            >
              <svg
                className="w-4 h-4 mr-1.5 text-slate-500 shrink-0"
                fill="none"
                viewBox="0 0 24 24"
                stroke="currentColor"
                strokeWidth={2}
              >

                  <path
                    strokeLinecap="round"
                    strokeLinejoin="round"
                    d="M9 15L3 9m0 0l6-6M3 9h12a6 6 0 010 12h-3"
                  />
              </svg>
              <span>Rouvrir le signalement</span>
            </Button>
          )}

          {!isTreated && (
            <div
              className={`grid grid-cols-1 ${
                normType === 'user' ? 'sm:grid-cols-2' : 'sm:grid-cols-3'
              } gap-2 w-full`}
            >
              {onReject && (
                <Button
                  variant="ghost"
                  size="sm"
                  fullWidth
                  isLoading={isProcessing}
                  onClick={() => onReject(report)}
                  className="w-full text-xs font-semibold px-2 py-2.5 justify-center"
                >
                  Rejeter
                </Button>
              )}

              {onBlockUser && (normType === 'listing' || normType === 'message' || normType === 'user' || normType === 'review') && (
                <Button
                  variant={normType === 'user' ? 'danger' : 'outline'}
                  size="sm"
                  fullWidth
                  isLoading={isProcessing}
                  onClick={() => onBlockUser(report)}
                  className={
                    normType === 'user'
                      ? 'w-full text-xs font-semibold px-1 sm:px-2 py-2.5 justify-center'
                      : 'w-full text-xs font-semibold px-1 sm:px-2 py-2.5 text-amber-800 border-amber-300 hover:bg-amber-50 hover:border-amber-400 bg-white justify-center'
                  }
                >
                  <svg
                    className={`w-3.5 h-3.5 mr-1 shrink-0 ${
                      normType === 'user' ? 'text-white' : 'text-amber-600'
                    }`}
                    fill="none"
                    viewBox="0 0 24 24"
                    stroke="currentColor"
                    strokeWidth={2}
                  >
                    <path
                      strokeLinecap="round"
                      strokeLinejoin="round"
                      d="M18.364 18.364A9 9 0 005.636 5.636m12.728 12.728A9 9 0 015.636 5.636m12.728 12.728L5.636 5.636"
                    />
                  </svg>
                  <span className="truncate">Bloquer l&apos;utilisateur</span>
                </Button>
              )}

              {onDelete && normType !== 'user' && (
                <Button
                  variant="danger"
                  size="sm"
                  fullWidth
                  isLoading={isProcessing}
                  onClick={() => onDelete(report)}
                  className="w-full text-xs font-semibold px-1 sm:px-2 py-2.5 justify-center"
                >
                  <span className="truncate">
                    {normType === 'listing'
                      ? "Supprimer l'annonce"
                      : normType === 'message'
                      ? 'Supprimer le message'
                      : normType === 'review'
                      ? "Supprimer l'avis"
                      : 'Supprimer'}
                  </span>
                </Button>
              )}
            </div>
          )}
        </div>
      )}
    </Card>
  );
}

export default ReportCard;
