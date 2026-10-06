import type { ConversationSummary, Message } from "@/types";
import { fetchApi } from "./client";

export const conversationsApi = {
	// List a user's conversations
	async list(): Promise<ConversationSummary[]> {
		return fetchApi<ConversationSummary[]>('/conversations');
	},

	// Find or create a conversation about a listing
	async getOrCreateListing(listingRef: string): Promise<ConversationSummary | null> {
		return fetchApi<ConversationSummary>('/conversations/listing', {
			method: 'POST',
			body: JSON.stringify({ listing_id: listingRef }),
		});
	},

	// Mark the listing as sold to the other participant
	async markAsSold(conversationId: string): Promise<ConversationSummary> {
		return fetchApi<ConversationSummary>(`/conversations/${conversationId}/mark-sold`, {
			method: 'POST',
		});
	},
};

export const messagesApi = {
	// List a conversation's messages (before_id pages the older ones)
	async list(conversationId: string, beforeId?: string | number): Promise<Message[]> {
		const query = beforeId != null ? `?before_id=${beforeId}` : "";
		return fetchApi<Message[]>(`/conversations/${conversationId}/messages${query}`);
	},

	// Send a message in a conversation
	async send(conversationId: string, body: string, _senderId?: string): Promise<Message> {
		return fetchApi<Message>(`/conversations/${conversationId}/messages`, {
			method: 'POST',
			body: JSON.stringify({ body }),
		});
	},
};
