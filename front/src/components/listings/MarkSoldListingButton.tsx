"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { Button } from "@/components/ui/Button";
import { Modal } from "@/components/ui/Modal";
import { listingsApi } from "@/lib/api/listings";
import { useCurrentUser } from "@/hooks/useCurrentUser";

export interface MarkSoldListingButtonProps {
	listingId: string;
	sellerId?: string | null;
	sellerPublicId?: string | null;
	status?: string;
}

export function MarkSoldListingButton({
	listingId,
	sellerId,
	sellerPublicId,
	status,
}: MarkSoldListingButtonProps) {
	const router = useRouter();
	const { user } = useCurrentUser();
	const [isOpen, setIsOpen] = useState(false);
	const [isLoading, setIsLoading] = useState(false);
	const [error, setError] = useState<string | null>(null);

	const isOwner =
		!!user &&
		((sellerId != null && String(user.id) === String(sellerId)) ||
			(sellerPublicId != null && String(user.public_id) === String(sellerPublicId)));

	if (!isOwner || status !== "active") return null;

	const handleMarkSold = async () => {
		setIsLoading(true);
		setError(null);
		try {
			await listingsApi.markSold(listingId);
			setIsOpen(false);
			router.refresh();
		} catch (err) {
			setError(err instanceof Error ? err.message : "Erreur lors du marquage comme vendu");
			setIsLoading(false);
		}
	};

	return (
		<>
			<Button
				type="button"
				size="lg"
				className="bg-brand-42-light hover:bg-brand-42 text-slate-950"
				fullWidth
				onClick={() => setIsOpen(true)}
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
						d="M9 12.75L11.25 15 15 9.75M21 12a9 9 0 11-18 0 9 9 0 0118 0z"
					/>
				</svg>
				<span>Signaler comme vendu</span>
			</Button>

			<Modal
				isOpen={isOpen}
				onClose={() => setIsOpen(false)}
				title="Marquer comme vendu ?"
			>
				<div className="space-y-4 pt-1">
					<p className="text-sm text-gray-600 leading-relaxed">
						Confirmer que cette annonce a été vendue ? Elle ne sera plus proposée dans les
						annonces actives et apparaîtra comme « vendue ».
					</p>

					{error && <p className="text-sm text-rose-600">{error}</p>}

					<div className="flex items-center justify-end gap-3 pt-4 border-t border-gray-100">
						<Button
							type="button"
							variant="outline"
							onClick={() => setIsOpen(false)}
							disabled={isLoading}
						>
							Annuler
						</Button>
						<Button
							type="button"
							onClick={handleMarkSold}
							isLoading={isLoading}
							disabled={isLoading}
						>
							Oui, marquer comme vendu
						</Button>
					</div>
				</div>
			</Modal>
		</>
	);
}
