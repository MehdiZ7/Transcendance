import type {
	PublicUser,
	UserProfile,
	UpdateUserInput,
	User,
	AdminUser,
	AdminUserFilterParams,
	PaginatedResponse,
	UserRole,
	MyStats
} from "@/types";
import { fetchApi } from "./client";

export const usersApi = {
	// function to retrieve the profile of a user
	async getByRef(ref: string): Promise<UserProfile | null> {
		try {
			return await fetchApi<UserProfile>(`/users/${ref}`);
		} catch {
			return null;
		}
	},
	// function to retrieve the profile of the current user (me), null when anonymous
	async getCurrent(): Promise<UserProfile | null> {
		return (await fetchApi<UserProfile | null>(`/users/me`)) ?? null;
	},
	// function to retrieve the personal statistics of the current user
	async getMyStats(): Promise<MyStats> {
		return fetchApi<MyStats>(`/users/me/stats`);
	},
	// function to update the information of a user
	async update(data: UpdateUserInput): Promise<User> {
		return fetchApi<User>(`/users/me`, {
			method: 'PATCH',
			body: JSON.stringify(data),
		});
	},
	// suspend/block a user
	async block(userId: string): Promise<void> {
		await fetchApi<void>(`/users/${userId}/block`, { method: 'POST' });
	},
	// unblock a user
	async unblock(userId: string): Promise<void> {
		await fetchApi<void>(`/users/${userId}/block`, { method: 'DELETE' });
	},
	// users blocked by the current user
	async getBlocked(): Promise<PublicUser[]> {
		return fetchApi<PublicUser[]>(`/users/me/blocks`);
	},
	// admin: list all users with pagination, search (q), and role filter
	async listUsers(params: AdminUserFilterParams = {}): Promise<PaginatedResponse<AdminUser>> {
		const query = new URLSearchParams();
		if (params.page !== undefined) query.set('page', String(params.page));
		if (params.limit !== undefined) query.set('limit', String(params.limit));
		if (params.q !== undefined && params.q.trim() !== '') query.set('q', params.q.trim());
		if (params.role !== undefined && params.role !== 'all' && params.role.trim() !== '') {
			query.set('role', params.role.trim());
		}
		const qs = query.toString();
		return fetchApi<PaginatedResponse<AdminUser>>(`/users${qs ? `?${qs}` : ''}`);
	},
	// admin: change role of a user
	async updateUserRole(publicId: string, role: UserRole): Promise<AdminUser> {
		return fetchApi<AdminUser>(`/users/${publicId}/role`, {
			method: 'PATCH',
			body: JSON.stringify({ role }),
		});
	},
	// admin: permanently delete a user (cascade delete)
	async deleteUser(publicId: string): Promise<void> {
		await fetchApi<void>(`/users/${publicId}`, {
			method: 'DELETE',
		});
	},
};
