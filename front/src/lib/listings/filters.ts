import { MAX_PAGE, MAX_PRICE, MAX_SEARCH_LENGTH } from "@/lib/limits";

// Sort values the API accepts (backend SortOption in api/v1/listings.py).
export const LISTING_SORTS = ["recent", "oldest", "price_asc", "price_desc", "likes_desc"] as const;

// Parse the "page" query param into a valid API page number (1..MAX_PAGE).
export function parsePage(raw?: string): number {
  if (raw === undefined || !/^\d+$/.test(raw)) return 1;
  const page = Number.parseInt(raw, 10);
  return page >= 1 && page <= MAX_PAGE ? page : 1;
}

// Parse a DB id (category/location) into a positive int, or drop it if invalid.
export function parseOptionalId(raw?: string): number | undefined {
  if (raw === undefined || !/^\d+$/.test(raw)) return undefined;
  const id = Number.parseInt(raw, 10);
  return id >= 1 ? id : undefined;
}

// Parse a price into 0..MAX_PRICE (clamped), or drop it if not a valid integer.
export function parsePrice(raw?: string): number | undefined {
  if (raw === undefined || !/^\d+$/.test(raw)) return undefined;
  return Math.min(Number.parseInt(raw, 10), MAX_PRICE);
}

// Keep only a sort value the API accepts, defaulting to "recent".
export function parseSort(raw?: string): string {
  return raw !== undefined && (LISTING_SORTS as readonly string[]).includes(raw) ? raw : "recent";
}

// Strip control characters (incl. NUL) and cap the search at MAX_SEARCH_LENGTH.
export function parseQuery(raw?: string): string {
  if (!raw) return "";
  return raw.replace(/[\u0000-\u001f\u007f]/g, " ").trim().toLowerCase().slice(0, MAX_SEARCH_LENGTH);
}
