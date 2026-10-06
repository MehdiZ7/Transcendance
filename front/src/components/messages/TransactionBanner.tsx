"use client";

import { useState } from "react";
import { Button } from "@/components/ui/Button";
import { Modal } from "@/components/ui/Modal";
import type { ConversationSummary } from "@/types/message";

// Compare two ids case-insensitively, tolerating null/undefined.
const sameId = (a?: string | null, b?: string | null): boolean =>
  Boolean(a && b && a.toLowerCase() === b.toLowerCase());

export interface TransactionBannerProps {
  conversation: ConversationSummary;
  currentUserId: string;
  onMarkAsSold: (conversationId: string) => Promise<void> | void;
  onOpenReviewModal: () => void;
  isMarkingSold?: boolean;
}

export function TransactionBanner({
  conversation,
  currentUserId,
  onMarkAsSold,
  onOpenReviewModal,
  isMarkingSold = false,
}: TransactionBannerProps) {
  const [isConfirmModalOpen, setIsConfirmModalOpen] = useState(false);
  const [markSoldError, setMarkSoldError] = useState<string | null>(null);

  // If this conversation is not tied to a listing, do not render the banner
  if (!conversation.listing_id && !conversation.listing_title) {
    return null;
  }

  const otherPublicId = conversation.other_participant.public_id || conversation.other_participant.id;
  const isSeller = Boolean(
    (conversation.listing_seller_id &&
      currentUserId &&
      conversation.listing_seller_id.toLowerCase() === currentUserId.toLowerCase()) ||
    (conversation.listing_seller_id &&
      otherPublicId &&
      conversation.listing_seller_id.toLowerCase() !== otherPublicId.toLowerCase())
  );

  const isBuyer = !isSeller;
  const status = conversation.listing_status?.toLowerCase();
  const isActive = status === "active";
  const isSold = status === "sold";
  const isDeleted = status === "deleted";

  // No state below covers any other status (draft, expired, archived, unknown):
  // render nothing rather than an empty bar
  if (!isActive && !isSold && !isDeleted) {
    return null;
  }

  const hasReviewed = !!conversation.has_reviewed;
  const otherName = conversation.other_participant.display_name;

  // Only the buyer recorded on the sale (listing_buyer_id) is the winning buyer.
  const isWinningBuyer = sameId(conversation.listing_buyer_id, currentUserId);
  // The seller only sold to this conversation's participant if it matches.
  const soldToOther = sameId(conversation.listing_buyer_id, otherPublicId);

  const handleConfirmMarkAsSold = async () => {
    setMarkSoldError(null);
    try {
      await onMarkAsSold(conversation.id);
      setIsConfirmModalOpen(false);
    } catch (err) {
      setMarkSoldError(
        err instanceof Error ? err.message : "Erreur lors du marquage comme vendu",
      );
    }
  };

  return (
    <>
      <div className="border-b border-slate-200/80 bg-slate-50/70 px-4 py-3 flex flex-col sm:flex-row sm:items-center justify-between gap-3 text-xs">
        {/* State 1: Listing active, current user is SELLER */}
        {isActive && isSeller && (
          <div className="flex items-center justify-between w-full gap-3">
            <div className="flex items-center gap-2 text-slate-700">
              <span className="text-base" aria-hidden="true">
                📦
              </span>
              <span>
                Annonce en cours : <span className="font-semibold">{conversation.listing_title}</span>
              </span>
            </div>
            <Button
              type="button"
              variant="primary"
              size="sm"
              onClick={() => {
                setMarkSoldError(null);
                setIsConfirmModalOpen(true);
              }}
              isLoading={isMarkingSold}
              disabled={isMarkingSold}
              className="shrink-0 font-semibold"
            >
              ✓ Marquer comme vendu à {otherName}
            </Button>
          </div>
        )}

        {/* State 2: Listing active, current user is BUYER */}
        {isActive && isBuyer && (
          <div className="flex items-center justify-between w-full gap-2">
            <div className="flex items-center gap-2 text-slate-600">
              <span className="text-base" aria-hidden="true">
                💬
              </span>
              <span>
                Discussion pour l&apos;annonce :{" "}
                <span className="font-semibold text-slate-800">
                  {conversation.listing_title}
                </span>
              </span>
            </div>
            <span className="px-2 py-0.5 rounded-full bg-emerald-50 text-emerald-700 border border-emerald-200 text-[11px] font-semibold shrink-0">
              En vente
            </span>
          </div>
        )}

        {/* State 3: Listing SOLD, current user is BUYER */}
        {isSold && isBuyer && (
          <div className="flex flex-col sm:flex-row sm:items-center justify-between w-full gap-3 bg-gradient-to-r from-emerald-50/80 to-teal-50/80 -mx-4 -my-3 p-3.5 border-b border-emerald-100">
            <div className="flex items-start gap-2.5">
              <span className="text-xl shrink-0" aria-hidden="true">
                {hasReviewed ? "✓" : isWinningBuyer ? "🎉" : "📦"}
              </span>
              <div>
                <p className="font-bold text-slate-900 text-xs sm:text-sm">
                  {hasReviewed
                    ? "Transaction évaluée !"
                    : isWinningBuyer
                    ? "Annonce vendue !"
                    : "Annonce vendue"}
                </p>
                <p className="text-slate-600 text-xs mt-0.5">
                  {hasReviewed
                    ? `Vous avez déposé un avis sur votre échange avec ${otherName}. Merci pour votre retour !`
                    : isWinningBuyer
                    ? `Cette annonce a été vendue par ${otherName}. Vous pouvez maintenant laisser votre avis d'évaluation sur le vendeur.`
                    : `Cette annonce a été vendue à un autre acheteur.`}
                </p>
              </div>
            </div>
            {!hasReviewed && isWinningBuyer && (
              <Button
                type="button"
                variant="primary"
                size="sm"
                onClick={onOpenReviewModal}
                className="shrink-0 font-bold shadow-xs"
              >
                ⭐ Laisser un avis
              </Button>
            )}
          </div>
        )}

        {/* State 4: Listing SOLD, current user is SELLER */}
        {isSold && isSeller && (
          <div className="flex items-center justify-between w-full gap-2 text-slate-700">
            <div className="flex items-center gap-2">
              <span className="text-emerald-600 font-bold text-sm" aria-hidden="true">
                ✓
              </span>
              {soldToOther ? (
                <span>
                  Annonce vendue à <span className="font-bold text-slate-900">{otherName}</span>.
                </span>
              ) : (
                <span>Annonce vendue à un autre acheteur.</span>
              )}
              {soldToOther && (
                <span className="text-slate-400 italic hidden sm:inline">
                  {hasReviewed ? "(Avis acheteur reçu)" : "(En attente de l'avis de l'acheteur)"}
                </span>
              )}
            </div>
            <span className="px-2.5 py-0.5 rounded-full bg-slate-200/80 text-slate-700 text-[11px] font-semibold shrink-0">
              Vendu
            </span>
          </div>
        )}

        {/* State 5: Listing DELETED */}
        {isDeleted && (
          <div className="flex items-center justify-between w-full gap-2 text-slate-500">
            <div className="flex items-center gap-2">
              <span className="text-base" aria-hidden="true">
                🗑️
              </span>
              <span>
                {conversation.listing_title ? (
                  <>
                    Annonce :{" "}
                    <span className="font-semibold text-slate-600 line-through">
                      {conversation.listing_title}
                    </span>
                  </>
                ) : (
                  "Cette annonce a été supprimée"
                )}
              </span>
            </div>
            <span className="px-2.5 py-0.5 rounded-full bg-slate-200 text-slate-700 border border-slate-300 text-[11px] font-semibold shrink-0">
              Supprimée
            </span>
          </div>
        )}
      </div>

      {/* Confirmation modal for marking as sold */}
      {isActive && isSeller && (
        <Modal
          isOpen={isConfirmModalOpen}
          onClose={() => setIsConfirmModalOpen(false)}
          title="Confirmer la vente"
        >
        <div className="space-y-4 pt-1">
          <p className="text-sm text-slate-600 leading-relaxed">
            Êtes-vous sûr de vouloir marquer l&apos;annonce{" "}
            <span className="font-semibold text-slate-900">
              « {conversation.listing_title} »
            </span>{" "}
            comme vendue à <span className="font-bold text-slate-900">{otherName}</span> ?
          </p>
          <p className="text-xs text-slate-500 bg-amber-50 p-3 rounded-xl border border-amber-100">
            💡 Cette action mettra à jour l&apos;annonce en statut <strong>Vendu</strong> et
            permettra à {otherName} de vous laisser un avis d&apos;évaluation sur votre profil.
          </p>
          {markSoldError && (
            <p role="alert" className="text-sm text-rose-600 font-medium">
              {markSoldError}
            </p>
          )}
          <div className="flex items-center justify-end gap-3 pt-4 border-t border-slate-100">
            <Button
              type="button"
              variant="outline"
              size="sm"
              onClick={() => setIsConfirmModalOpen(false)}
              disabled={isMarkingSold}
            >
              Annuler
            </Button>
            <Button
              type="button"
              variant="primary"
              size="sm"
              onClick={handleConfirmMarkAsSold}
              isLoading={isMarkingSold}
              disabled={isMarkingSold}
            >
              Oui, marquer comme vendu
            </Button>
          </div>
        </div>
      </Modal>
      )}
    </>
  );
}
