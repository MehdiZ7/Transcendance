import { test, expect, goto, AUTH } from './helpers';

test.describe('analytics — RBAC', () => {
  test.use({ storageState: AUTH.user });

  test('a plain user is redirected away from /analytics', async ({ page }) => {
    await page.goto('/analytics');
    await expect(page).toHaveURL(/\/$/, { timeout: 20_000 });
  });
});

test.describe('analytics — admin', () => {
  test('renders the dashboard and the export action', async ({ page }) => {
    await goto(page, '/analytics');
    await expect(page.getByRole('heading', { name: 'Dashboard' })).toBeVisible({
      timeout: 20_000,
    });
    await expect(page.getByRole('button', { name: /Exporter/ })).toBeVisible();
  });
});
