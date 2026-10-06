"use client";

import { MAX_REVIEW_LENGTH } from "@/lib/limits";
import { useState } from "react";
import { Modal } from "@/components/ui/Modal";
import { Button } from "@/components/ui/Button";
import { Avatar } from "@/components/ui/Avatar";
import type { PublicUser } from "@/types/user";
import type { Review } from "@/types/report";
import { reviewsApi } from "@/lib/api/reviews";

export interface ReviewModalProps {
  isOpen: boolean;
  onClose: () => void;
  conversationId: string;
  seller: PublicUser;
  listingTitle?: string | null;
  onSuccess: (review: Review) => void;
}

const RATING_LABELS: Record<number, string> = {
  1: "1/5 — Très décevant",
  2: "2/5 — Décevant",
  3: "3/5 — Moyen / Conforme",
  4: "4/5 — Très bien",
  5: "5/5 — Parfait !",
};

export function ReviewModal({
  isOpen,
  onClose,
  conversationId,
  seller,
  listingTitle,
  onSuccess,
}: ReviewModalProps) {
  const [rating, setRating] = useState<number>(5);
  const [hoverRating, setHoverRating] = useState<number>(0);
  const [body, setBody] = useState("");
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const activeRating = hoverRating || rating;

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (rating < 1 || rating > 5) {
      setError("Veuillez sélectionner une note entre 1 et 5 étoiles.");
      return;
    }
    if (body.trim().length < 5) {
      setError("Le commentaire doit contenir au moins 5 caractères.");
      return;
    }

    setIsSubmitting(true);
    setError(null);

    try {
      const review = await reviewsApi.create({
        conversation_id: conversationId,
        subject_id: seller.public_id || seller.id,
        rating,
        body: body.trim(),
      });
      onSuccess(review);
      onClose();
      setBody("");
      setRating(5);
    } catch (err) {
      setError(
        err instanceof Error
          ? err.message
          : "Une erreur est survenue lors de l'enregistrement de votre avis."
      );
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <Modal isOpen={isOpen} onClose={onClose} title="Laisser un avis sur la transaction">
      <form onSubmit={handleSubmit} className="space-y-5 pt-1">
        {/* Seller and listing reminder */}
        <div className="flex items-center gap-3 p-3 bg-slate-50 rounded-xl border border-slate-100">
          <Avatar
            src={seller.avatar_path ?? undefined}
            alt={seller.display_name}
            size="md"
          />
          <div className="min-w-0 flex-1">
            <p className="text-sm font-bold text-slate-900 truncate">
              {seller.display_name}
            </p>
            {listingTitle ? (
              <p className="text-xs text-slate-500 truncate">
                Pour l&apos;annonce : <span className="font-medium text-slate-700">{listingTitle}</span>
              </p>
            ) : (
              <p className="text-xs text-slate-500">Vendeur</p>
            )}
          </div>
        </div>

        {/* Star rating selector */}
        <div>
          <label className="block text-sm font-semibold text-slate-700 mb-2">
            Note globale
          </label>
          <div className="flex items-center gap-1.5" onMouseLeave={() => setHoverRating(0)}>
            {[1, 2, 3, 4, 5].map((star) => (
              <button
                key={star}
                type="button"
                className="p-1 text-2xl transition-transform hover:scale-110 focus:outline-none"
                onClick={() => setRating(star)}
                onMouseEnter={() => setHoverRating(star)}
                aria-label={`Attribuer la note de ${star} sur 5`}
              >
                <svg
                  className={`w-7 h-7 transition-colors ${
                    star <= activeRating
                      ? "text-amber-400 fill-amber-400"
                      : "text-slate-200 fill-slate-100 hover:text-amber-200"
                  }`}
                  viewBox="0 0 24 24"
                  stroke="currentColor"
                  strokeWidth={1.5}
                >
                  <path
                    strokeLinecap="round"
                    strokeLinejoin="round"
                    d="M11.48 3.499a.562.562 0 011.04 0l2.125 5.111a.563.563 0 00.475.345l5.518.442c.499.04.701.663.321.988l-4.204 3.602a.563.563 0 00-.182.557l1.285 5.385a.562.562 0 01-.84.61l-4.725-2.885a.563.563 0 00-.586 0L6.982 20.54a.562.562 0 01-.84-.61l1.285-5.386a.562.562 0 00-.182-.557l-4.204-3.602a.563.563 0 01.321-.988l5.518-.442a.563.563 0 00.475-.345L11.48 3.5z"
                  />
                </svg>
              </button>
            ))}
            <span className="ml-3 text-xs font-semibold text-amber-600 bg-amber-50 px-2.5 py-1 rounded-md border border-amber-100">
              {RATING_LABELS[activeRating]}
            </span>
          </div>
        </div>

        {/* Commentaire */}
        <div>
          <label className="block text-sm font-semibold text-slate-700 mb-1">
            Votre commentaire
          </label>
          <p className="text-xs text-slate-500 mb-2">
            Partagez votre expérience sur la ponctualité, l&apos;état de l&apos;objet et l&apos;échange avec ce membre.
          </p>
          <textarea
            value={body}
            onChange={(e) => setBody(e.target.value)}
            rows={4}
            maxLength={MAX_REVIEW_LENGTH}
            placeholder="Ex : Vendeur très réactif et ponctuel au cluster E2. L'objet était exactement dans l'état décrit, je recommande sans hésiter !"
            className="w-full p-3 border border-slate-200 rounded-xl text-sm focus:outline-none focus:ring-2 focus:ring-[#00babc] focus:border-transparent resize-none text-slate-800 placeholder-slate-400"
            required
            minLength={5}
          />
        </div>

        {error && (
          <div className="p-3 bg-rose-50 border border-rose-200 rounded-xl text-xs font-medium text-rose-600">
            {error}
          </div>
        )}

        {/* Actions */}
        <div className="flex items-center justify-end gap-3 pt-3 border-t border-slate-100">
          <Button
            type="button"
            variant="outline"
            size="sm"
            onClick={onClose}
            disabled={isSubmitting}
          >
            Annuler
          </Button>
          <Button
            type="submit"
            variant="primary"
            size="sm"
            isLoading={isSubmitting}
            disabled={isSubmitting || body.trim().length < 5}
          >
            Publier mon avis
          </Button>
        </div>
      </form>
    </Modal>
  );
}
