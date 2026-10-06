import type { Review, CreateReviewInput } from "@/types";
import { fetchApi } from "./client";

export const reviewsApi = {
	// reviews received by a user
	async listByUser(userId: string): Promise<Review[]> {
		return fetchApi<Review[]>(`/users/${userId}/reviews`);
	},

	// leave a review after a transaction
	async create(data: CreateReviewInput): Promise<Review> {
		return fetchApi<Review>('/reviews', {
			method: 'POST',
			body: JSON.stringify({
				...data,
				conversation_id: Number(data.conversation_id),
			}),
		});
	},

	// delete a review (moderator or author)
	async delete(reviewId: string): Promise<void> {
		await fetchApi<void>(`/reviews/${reviewId}`, { method: 'DELETE' });
	},
};
