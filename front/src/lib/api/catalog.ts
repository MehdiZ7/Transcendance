import type { Category, Location } from "@/types";
import { fetchApi } from "./client";

export const catalogApi = {
	async getCategories(): Promise<Category[]> {
		return fetchApi<Category[]>('/categories');
	},
	async getLocations(): Promise<Location[]> {
		return fetchApi<Location[]>('/locations');
	},
};
