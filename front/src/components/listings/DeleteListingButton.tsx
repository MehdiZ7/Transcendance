"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { Button } from "@/components/ui/Button";
import { Modal } from "@/components/ui/Modal";
import { listingsApi } from "@/lib/api/listings";
import { useCurrentUser } from "@/hooks/useCurrentUser";

export interface DeleteListingButtonProps {
	listingId: string;
	sellerId?: string | null;
	sellerPublicId?: string | null;
}

export function DeleteListingButton({
	listingId,
	sellerId,
	sellerPublicId,
}: DeleteListingButtonProps) {
	const router = useRouter();
	const { user } = useCurrentUser();
	const [isOpen, setIsOpen] = useState(false);
	const [isDeleting, setIsDeleting] = useState(false);
	const [error, setError] = useState<string | null>(null);

	const isOwner =
		!!user &&
		((sellerId != null && String(user.id) === String(sellerId)) ||
			(sellerPublicId != null && String(user.public_id) === String(sellerPublicId)));
	if (!isOwner) return null;

	const handleDelete = async () => {
		setIsDeleting(true);
		setError(null);
		try {
			await listingsApi.delete(listingId);
			router.push("/");
		} catch (err) {
			setError(err instanceof Error ? err.message : "Erreur lors de la suppression");
			setIsDeleting(false);
		}
	};

	return (
		<>
			<Button
				type="button"
				size="lg"
				className="bg-red-600 hover:bg-red-500 "
				fullWidth
				onClick={() => setIsOpen(true)}
			>
				<svg
					className="w-4 h-4 stroke-white"
					fill="none"
					viewBox="0 0 24 24"
					strokeWidth={2}
				>
					<path
						strokeLinecap="round"
						strokeLinejoin="round"
						d="M14.74 9l-.346 9m-4.788 0L9.26 9m9.968-3.21c.342.052.682.107 1.022.166m-1.022-.165L18.16 19.673a2.25 2.25 0 01-2.244 2.077H8.084a2.25 2.25 0 01-2.244-2.077L4.772 5.79m14.456 0a48.108 48.108 0 00-3.478-.397m-12 .562c.34-.059.68-.114 1.022-.165m0 0a48.11 48.11 0 013.478-.397m7.5 0v-.916c0-1.18-.91-2.164-2.09-2.201a51.964 51.964 0 00-3.32 0c-1.18.037-2.09 1.022-2.09 2.201v.916m7.5 0a48.667 48.667 0 00-7.5 0"
					/>
				</svg>
				<span>Supprimer l&apos;annonce</span>
			</Button>

			<Modal
				isOpen={isOpen}
				onClose={() => setIsOpen(false)}
				title="Supprimer l'annonce ?"
			>
				<div className="space-y-4 pt-1">
					<p className="text-sm text-gray-600 leading-relaxed">
						Êtes-vous sûr de vouloir supprimer cette annonce ? Cette action est irréversible.
					</p>

					{error && <p className="text-sm text-rose-600">{error}</p>}

					<div className="flex items-center justify-end gap-3 pt-4 border-t border-gray-100">
						<Button
							type="button"
							variant="outline"
							onClick={() => setIsOpen(false)}
							disabled={isDeleting}
						>
							Annuler
						</Button>
						<Button
							type="button"
							variant="danger"
							onClick={handleDelete}
							isLoading={isDeleting}
							disabled={isDeleting}
						>
							Oui, supprimer
						</Button>
					</div>
				</div>
			</Modal>
		</>
	);
}
