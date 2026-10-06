import type { CreateReportInput, Report } from '@/types';
import { fetchApi } from "./client";

export const reportsApi = {
	// List all reports
	async getAll(): Promise<Report[]> {
		return fetchApi<Report[]>('/reports');
	},

	// Create a report
	async create(data: CreateReportInput, _extra?: { target?: Report['target'] }): Promise<Report> {
		return fetchApi<Report>('/reports', {
			method: 'POST',
			body: JSON.stringify({
				...data,
				target_id: String(data.target_id),
			}),
		});
	},

	// Reject a report (close without action)
	async reject(reportId: string): Promise<Report> {
		return fetchApi<Report>(`/reports/${reportId}/reject`, {
			method: 'POST',
		});
	},

	// Resolve a report by deleting the reported content
	async deleteTarget(reportId: string, targetType: Report['target_type'], targetId: string): Promise<Report> {
		return fetchApi<Report>(`/reports/${reportId}/resolve`, {
			method: 'POST',
			body: JSON.stringify({ action: 'delete_target', target_type: targetType, target_id: targetId }),
		});
	},

	// Resolve a report by blocking the reported user
	async blockUser(reportId: string, userId: string): Promise<Report> {
		return fetchApi<Report>(`/reports/${reportId}/resolve`, {
			method: 'POST',
			body: JSON.stringify({ action: 'block_user', user_id: userId }),
		});
	},

	// Reopen a closed/resolved report, restoring what had been removed
	// (listing, message, review) - otherwise the backend just flips the
	// status to "open" without restoring anything.
	async reopen(reportId: string): Promise<Report> {
		return fetchApi<Report>(`/reports/${reportId}/reopen`, {
			method: 'POST',
			body: JSON.stringify({ action: 'restore_target' }),
		});
	},

	// Unblock a user and reopen the report
	async unblockUser(reportId: string, userId: string): Promise<Report> {
		return fetchApi<Report>(`/reports/${reportId}/reopen`, {
			method: 'POST',
			body: JSON.stringify({ action: 'unblock_user', user_id: userId }),
		});
	},
};
