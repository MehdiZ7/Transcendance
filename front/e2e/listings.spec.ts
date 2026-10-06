import { test, expect, goto } from './helpers';

test.describe('listings home', () => {
  test('renders listing cards', async ({ page }) => {
    await goto(page, '/');
    await expect(page.locator('a[href^="/listings/"]').filter({ has: page.locator('h3') }).first()).toBeVisible();
  });

  test('search updates the URL', async ({ page }) => {
    await goto(page, '/');
    const search = page.getByPlaceholder(/Rechercher/);
    // Retry the input only: it is client-side (hydration race), most visible on WebKit.
    await expect(async () => {
      await search.fill('clavier');
      await search.press('Enter');
      await expect(page).toHaveURL(/[?&]q=clavier/, { timeout: 3000 });
    }).toPass({ timeout: 20_000 });
  });

  test('location filter is applied from the URL', async ({ page }) => {
    await goto(page, '/?location=5');
    await expect(page.locator('select').first()).toHaveValue('5');
  });

  test('filter modal opens', async ({ page }) => {
    await goto(page, '/');
    // Retry the click: it is a client button and may not be hydrated yet.
    await expect(async () => {
      await page.getByRole('button', { name: /Filtres/ }).click();
      await expect(page.getByText('Filtres & Tri')).toBeVisible({ timeout: 2000 });
    }).toPass({ timeout: 20_000 });
    await expect(page.locator('input[name="sort"]').first()).toBeVisible();
  });

  test('reset filters clears the query', async ({ page }) => {
    // Retry: the reset button is client-side (hydration race).
    await expect(async () => {
      await goto(page, '/?q=clavier');
      await page.getByRole('button', { name: /Réinitialiser/ }).first().click();
      await page.getByRole('button', { name: /Oui, réinitialiser/ }).click({ timeout: 5000 });
      await expect(page).toHaveURL(/\/$/, { timeout: 5000 });
    }).toPass({ timeout: 40_000 });
  });
});
