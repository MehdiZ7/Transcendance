/**
 * Image resolver utility for LeBon42.
 * Unifies resolution of local SVGs, 42 profile picture URLs, uploaded files
 * served by nginx under /media/..., and data:/blob: URLs kept only as a
 * fallback for values stored before real uploads existed - nothing produces
 * them anymore.
 */

export const DEFAULT_LISTING_IMAGE = '/mock/placeholders/default-listing.svg';

export const CATEGORY_PLACEHOLDERS: Record<string, string> = {
  'cat-objet': '/mock/placeholders/cat-objet.svg',
  'cat-cours': '/mock/placeholders/cat-cours.svg',
  'cat-covoiturage': '/mock/placeholders/cat-covoiturage.svg',
  'cat-service': '/mock/placeholders/cat-service.svg',
  'cat-logement': '/mock/placeholders/cat-logement.svg',
};

/**
 * Returns a themed SVG placeholder according to the category ID.
 */
export function getDefaultImageForCategory(categoryId?: string | null): string {
  if (categoryId && CATEGORY_PLACEHOLDERS[categoryId]) {
    return CATEGORY_PLACEHOLDERS[categoryId];
  }
  return DEFAULT_LISTING_IMAGE;
}

/**
 * Resolves a storage_path or image URL into a displayable web URL.
 * Transparently supports:
 * - Remote HTTP/HTTPS URLs (e.g. 42 profile pictures)
 * - Public local assets (/mock/placeholders/...) and uploads (/media/images/...)
 * - Data/blob URLs, kept only for values stored before real uploads existed
 */
export function getImageUrl(
  storagePath?: string | null,
  categoryId?: string | null
): string {
  if (!storagePath || storagePath.trim() === '') {
    return getDefaultImageForCategory(categoryId);
  }

  // Legacy data/blob URLs, from before uploads went through the server
  if (storagePath.startsWith('data:') || storagePath.startsWith('blob:')) {
    return storagePath;
  }

  // Already a full remote URL (e.g. a 42 profile picture)
  if (storagePath.startsWith('http://') || storagePath.startsWith('https://')) {
    return storagePath;
  }

  // Relative public asset served by Next.js, or an upload served by nginx
  if (storagePath.startsWith('/')) {
    return storagePath;
  }

  // Future MinIO / S3 object key or API route
  const backendBaseUrl = process.env.NEXT_PUBLIC_API_URL || '';
  return `${backendBaseUrl}/uploads/${storagePath}`;
}

/**
 * Determines whether Next.js Image component should disable optimization
 * (required for data: URLs, blobs, and vector SVGs).
 */
export function isUnoptimizedImage(url?: string | null): boolean {
  if (!url) return true;
  return (
    url.startsWith('data:') ||
    url.startsWith('blob:') ||
    url.startsWith('/media/') || // uploaded files: served by nginx, Next cannot fetch them
    url.endsWith('.svg') ||
    url.includes('.svg?')
  );
}
