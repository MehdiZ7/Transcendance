import { test, expect } from './helpers';

const PAGES = [
  '/',
  '/messages',
  '/profile',
  '/moderation',
  '/analytics',
  '/listings/create',
  '/privacy',
  '/terms',
];

for (const path of PAGES) {
  test(`page ${path} loads without JS error`, async ({ page }) => {
    const errors: string[] = [];
    page.on('pageerror', (e) => errors.push(e.message));

    await page.goto(path);
    await expect(page.locator('body')).toBeVisible();

    expect(errors).toEqual([]);
  });
}
