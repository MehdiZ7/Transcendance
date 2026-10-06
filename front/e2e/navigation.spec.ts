import { test, expect, AUTH, goto } from './helpers';

test.describe('navigation — admin', () => {
  test('shows every nav item', async ({ page }) => {
    await goto(page, '/');
    const header = page.locator('header');

    await expect(header.getByRole('link', { name: 'Annonces' })).toBeVisible();
    await expect(header.getByRole('link', { name: 'Profil' })).toBeVisible();
    await expect(header.getByRole('link', { name: 'Messages' })).toBeVisible();
    await expect(header.getByRole('link', { name: 'Moderation' })).toBeVisible();
    await expect(header.getByRole('link', { name: 'Analytics' })).toBeVisible();
  });
});

test.describe('navigation — user', () => {
  test.use({ storageState: AUTH.user });

  test('hides moderator/admin items', async ({ page }) => {
    await goto(page, '/');
    const header = page.locator('header');

    await expect(header.getByRole('link', { name: 'Annonces' })).toBeVisible();
    await expect(header.getByRole('link', { name: 'Moderation' })).toHaveCount(0);
    await expect(header.getByRole('link', { name: 'Analytics' })).toHaveCount(0);
  });
});

test.describe('navigation — moderator', () => {
  test.use({ storageState: AUTH.moderator });

  test('sees moderation but not analytics', async ({ page }) => {
    await goto(page, '/');
    const header = page.locator('header');

    await expect(header.getByRole('link', { name: 'Moderation' })).toBeVisible();
    await expect(header.getByRole('link', { name: 'Analytics' })).toHaveCount(0);
  });
});

test.describe('navigation — mobile', () => {
  test.use({ viewport: { width: 390, height: 844 } });

  test('opens the mobile menu', async ({ page }) => {
    await goto(page, '/');
    // Retry the click: the header is a client component (hydration race).
    await expect(async () => {
      await page.getByRole('button', { name: /Ouvrir le menu/ }).click();
      await expect(page.getByRole('link', { name: 'Messages' }).first()).toBeVisible({
        timeout: 2000,
      });
    }).toPass({ timeout: 20_000 });
  });
});
