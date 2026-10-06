import { test, expect, goto, AUTH } from './helpers';

test.describe('moderation — RBAC', () => {
  test.use({ storageState: AUTH.user });

  test('a plain user is redirected away from /moderation', async ({ page }) => {
    await page.goto('/moderation');
    await expect(page).toHaveURL(/\/$/, { timeout: 20_000 });
  });
});

test.describe('moderation — admin', () => {
  test('shows every moderation tab', async ({ page }) => {
    await goto(page, '/moderation');

    const tabs = page.getByRole('navigation', { name: 'Onglets de modération' });
    await expect(tabs).toBeVisible({ timeout: 20_000 });

    for (const label of ['Annonces', 'Messages', 'Utilisateurs', 'Avis', 'Historique']) {
      await expect(tabs.getByRole('button', { name: label })).toBeVisible();
    }
  });
});
