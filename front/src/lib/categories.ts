import type { Category } from '@/types/listing';

export const OBJECT_CATEGORY_ID = 'cat-objet';

/**
 * Checks whether a given category or category ID represents physical objects/items.
 */
export function isObjectCategory(
  category?: Category | string | number | null,
  categoriesList?: Category[]
): boolean {
  if (category === undefined || category === null) return false;

  // If a Category object is provided
  if (typeof category === 'object') {
    const idLower = String(category.id ?? '').toLowerCase().trim();
    const nameLower = String(category.category_name ?? '').toLowerCase().trim();
    return (
      idLower === '1' ||
      idLower === OBJECT_CATEGORY_ID ||
      idLower === 'cat-objet' ||
      idLower === 'objet' ||
      nameLower === 'objet' ||
      nameLower === 'objets' ||
      nameLower === 'item' ||
      nameLower === 'items'
    );
  }

  // If an ID is provided and a list of categories is available
  if (categoriesList && categoriesList.length > 0) {
    const matched = categoriesList.find((c) => String(c.id) === String(category));
    if (matched) {
      return isObjectCategory(matched);
    }
  }

  const str = String(category).toLowerCase().trim();
  return (
    str === '1' ||
    str === OBJECT_CATEGORY_ID ||
    str === 'cat-objet' ||
    str === 'objet' ||
    str === 'objets' ||
    str === 'item' ||
    str === 'items'
  );
}

/**
 * Checks whether a listing belongs to an object category.
 */
export function isListingAnObject(
  listing?: { category_id?: string | number | null; category?: Category | null } | null
): boolean {
  if (!listing) return false;
  return isObjectCategory(listing.category) || isObjectCategory(listing.category_id);
}
