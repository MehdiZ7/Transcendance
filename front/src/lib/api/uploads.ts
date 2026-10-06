import { fetchApi } from './client';

export const uploadsApi = {
	// Store an image on the server; the answer is the path to keep in
	// image_urls or avatar_path (served by nginx under /media/). The API checks
	// size and type itself: the checks in the dropzones are only a convenience.
	async uploadImage(file: File): Promise<string> {
		const form = new FormData();
		form.append('file', file);
		const { path } = await fetchApi<{ path: string }>('/uploads/images', {
			method: 'POST',
			body: form,
		});
		return path;
	},
};
