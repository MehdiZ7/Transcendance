// Size limits the API enforces (422 above them). Mirror of
// backend/src/app/schemas/limits.py: change both together. Used as `maxLength`
// on inputs so a user is stopped while typing instead of getting an error
// after sending.
export const MAX_MESSAGE_LENGTH = 2000;
export const MAX_REVIEW_LENGTH = 1000;
export const MAX_REPORT_REASON_LENGTH = 1000;
export const MAX_BIO_LENGTH = 500;
export const MAX_DISPLAY_NAME_LENGTH = 50;
export const MAX_LISTING_TITLE_LENGTH = 120;
export const MAX_LISTING_BODY_LENGTH = 5000;
export const MAX_PRICE = 10_000_000;
export const MAX_SEARCH_LENGTH = 100;
export const MAX_PAGE = 10_000;
export const MIN_PASSWORD_LENGTH = 8;
export const MAX_PASSWORD_LENGTH = 128;
// Analytics date range: MIN_ANALYTICS_DATE / MAX_ANALYTICS_DATE in limits.py,
// MAX_RANGE_DAYS in api/v1/analytics.py
export const MIN_ANALYTICS_DATE = "2000-01-01";
export const MAX_ANALYTICS_DATE = "2100-12-31";
export const MAX_ANALYTICS_RANGE_DAYS = 366;
