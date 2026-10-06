import { test, expect, goto } from './helpers';

/** First real listing card (excludes the header's "/listings/create" link). */
function firstCard(page: Parameters<typeof goto>[0]) {
  return page.locator('a[href^="/listings/"]').filter({ has: page.locator('h3') }).first();
}

test.describe('listing detail', () => {
  test('opens the first listing', async ({ page }) => {
    await goto(page, '/');
    await firstCard(page).click();
    await expect(page).toHaveURL(/\/listings\/.+/);
    await expect(page.getByRole('heading', { level: 1 })).toBeVisible();
  });

  test('toggles the favorite button', async ({ page }) => {
    await goto(page, '/');
    await firstCard(page).click();
    await expect(page.getByRole('heading', { level: 1 })).toBeVisible();
    // Wait until the session is loaded (auth state), else the click opens the
    // auth modal instead of toggling.
    await expect(page.getByRole('button', { name: 'Déconnexion' })).toBeVisible();

    const addFav = page.getByRole('button', { name: 'Ajouter aux favoris' });
    const removeFav = page.getByRole('button', { name: 'Retirer des favoris' });

    if (await addFav.count()) {
      await addFav.first().click();
      await expect(removeFav.first()).toBeVisible();
    } else {
      await removeFav.first().click();
      await expect(addFav.first()).toBeVisible();
    }
  });

  test('shows the report action', async ({ page }) => {
    await goto(page, '/');
    await firstCard(page).click();
    await expect(page.getByText(/Signaler cette annonce/)).toBeVisible();
  });
});
