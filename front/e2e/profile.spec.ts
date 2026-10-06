import { test, expect, goto } from './helpers';

function firstCard(page: Parameters<typeof goto>[0]) {
  return page.locator('a[href^="/listings/"]').filter({ has: page.locator('h3') }).first();
}

test.describe('profile — own', () => {
  test('loads and switches tabs', async ({ page }) => {
    await goto(page, '/profile');
    await expect(page.getByRole('heading', { level: 2 })).toBeVisible({ timeout: 20_000 });

    await page.getByRole('button', { name: /^Favoris/ }).click();
    await page.getByRole('button', { name: /^Avis/ }).click();
    await page.getByRole('button', { name: /^Annonces/ }).click();
  });

  test('opens the edit modal', async ({ page }) => {
    await goto(page, '/profile');
    await page.getByRole('button', { name: /Éditer le profil/ }).click();
    await expect(page.getByText('Nom de profil')).toBeVisible();
  });
});

test.describe('profile — another user', () => {
  test('shows friend and block actions', async ({ page }) => {
    await goto(page, '/');
    await firstCard(page).click();
    await page.getByText('Consulter le profil étudiant').click();

    await expect(page).toHaveURL(/\/profile\/.+/);
    await expect(page.getByRole('button', { name: /Bloquer|Débloquer/ })).toBeVisible({
      timeout: 20_000,
    });
  });
});
