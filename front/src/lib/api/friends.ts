import type { PublicUser, Friend, FriendMessage, FriendConversationSummary } from "@/types";
import { fetchApi } from "./client";

export const friendsApi = {
	// get the friend's list of a user
	async list(userId: string): Promise<PublicUser[]> {
		return fetchApi<PublicUser[]>(`/users/${userId}/friends`);
	},

	// get the pending requests of a user
	async listPending(_userId?: string): Promise<Friend[]> {
		return fetchApi<Friend[]>(`/friends/pending`);
	},

	// friend conversations, for the messages inbox
	async listConversations(): Promise<FriendConversationSummary[]> {
		return fetchApi<FriendConversationSummary[]>(`/friends/messages`);
	},

	// messages exchanged with one friend, newest page first (before_id pages older)
	async listMessages(publicId: string, beforeId?: string | number): Promise<FriendMessage[]> {
		const query = beforeId != null ? `?before_id=${beforeId}` : "";
		return fetchApi<FriendMessage[]>(`/friends/${publicId}/messages${query}`);
	},

	// send a direct message to a friend
	async sendMessage(publicId: string, body: string): Promise<FriendMessage> {
		return fetchApi<FriendMessage>(`/friends/${publicId}/messages`, {
			method: 'POST',
			body: JSON.stringify({ body }),
		});
	},

	// send a friend request
	async sendRequest(userId: string): Promise<void> {
		await fetchApi<void>(`/friends`, {
			method: 'POST',
			body: JSON.stringify({ user_id: userId }),
		});
	},

	// cancel an outgoing friend request
	async cancelRequest(userId: string): Promise<void> {
		await fetchApi<void>(`/friends/requests/${userId}`, { method: 'DELETE' });
	},

	// accept a friend request
	async accept(requestId: string): Promise<void> {
		await fetchApi<void>(`/friends/${requestId}/accept`, { method: 'POST' });
	},

	// decline a friend request
	async decline(requestId: string): Promise<void> {
		await fetchApi<void>(`/friends/${requestId}/decline`, { method: 'POST' });
	},

	// remove a friend
	async remove(userId: string): Promise<void> {
		await fetchApi<void>(`/friends/${userId}`, { method: 'DELETE' });
	},
};
