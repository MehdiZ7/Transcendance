"use client";

import { useState } from "react";
import { Button } from "@/components/ui/Button";
import { Modal } from "@/components/ui/Modal";
import { useCurrentUser } from "@/hooks/useCurrentUser";

export interface DeleteReviewButtonProps {
	reviewId: string;
	authorId?: string | null;
	authorPublicId?: string | null;
	onDelete: (reviewId: string) => Promise<void>;
}

export function DeleteReviewButton({
	reviewId,
	authorId,
	authorPublicId,
	onDelete,
}: DeleteReviewButtonProps) {
	const { user } = useCurrentUser();
	const [isOpen, setIsOpen] = useState(false);
	const [isDeleting, setIsDeleting] = useState(false);
	const [error, setError] = useState<string | null>(null);

	// the button only appears when im the autor 
	const isAuthor = !!user && (user.id === authorId || user.public_id === authorPublicId);
	if (!isAuthor) return null;

	const handleDelete = async () => {
		setIsDeleting(true);
		setError(null);
		try {
			await onDelete(reviewId);
			setIsOpen(false);
		} catch (err) {
			setError(err instanceof Error ? err.message : "Erreur lors de la suppression");
		} finally {
			setIsDeleting(false);
		}
	};

	return (
		<>
			<Button
				type="button"
				variant="ghost"
				size="sm"
				className="text-red-600 hover:text-red-700 hover:bg-red-50"
				title="Supprimer cet avis"
				onClick={() => setIsOpen(true)}
			>
				🗑️
			</Button>

			<Modal
				isOpen={isOpen}
				onClose={() => setIsOpen(false)}
				title="Supprimer cet avis ?"
			>
				<div className="space-y-4 pt-1">
					<p className="text-sm text-gray-600 leading-relaxed">
						Êtes-vous sûr de vouloir supprimer cet avis ? Cette action est irréversible.
					</p>

					{error && <p className="text-sm text-rose-600">{error}</p>}

					<div className="flex items-center justify-end gap-3 pt-4 border-t border-gray-100">
						<Button type="button" variant="outline" onClick={() => setIsOpen(false)} disabled={isDeleting}>
							Annuler
						</Button>
						<Button type="button" variant="danger" onClick={handleDelete} isLoading={isDeleting} disabled={isDeleting}>
							Oui, supprimer
						</Button>
					</div>
				</div>
			</Modal>
		</>
	);
}
