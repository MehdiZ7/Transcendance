import { test, expect, goto, uniqueSuffix } from './helpers';

test.describe('listing create', () => {
  // NOTE: the delete-cleanup step is intentionally omitted: the backend does
  // not expose `DELETE /listings/{id}` yet, so a created listing stays in the
  // dev database. Re-add the cleanup once that route exists.
  test('creates a listing from the form', async ({ page }) => {
    const title = `E2E Listing ${uniqueSuffix()}`;

    await goto(page, '/listings/create');

    await page.locator('#title').fill(title);
    await page.locator('#price').fill('10');

    await page.locator('#category_id').selectOption({ index: 0 });
    await page.locator('#location_id').selectOption({ index: 0 });

    // Condition radios (only shown for physical objects); pick the first one.
    const condition = page.locator('input[name="condition"]').first();
    if (await condition.count()) {
      await condition.check();
    }

    await page.locator('#body').fill('Annonce créée automatiquement par la suite E2E.');

    await page.getByRole('button', { name: /Publier l'annonce/ }).click();

    await expect(page).toHaveURL(/\/listings\/.+/, { timeout: 20_000 });
    await expect(page.getByRole('heading', { level: 1 })).toContainText(title);
  });
});
