import { test, expect } from './helpers';

test('the footer links to privacy and terms', async ({ page }) => {
  await page.goto('/');
  const footer = page.locator('footer');

  await expect(footer.getByRole('link', { name: 'Politique de confidentialité' })).toBeVisible();
  await expect(footer.getByRole('link', { name: /Conditions d.utilisation/ })).toBeVisible();
});

test('the privacy page has real content', async ({ page }) => {
  await page.goto('/privacy');

  await expect(page.getByRole('heading', { level: 1, name: 'Politique de confidentialité' })).toBeVisible();
  await expect(page.getByRole('heading', { name: 'Responsable du traitement' })).toBeVisible();
  await expect(page.getByRole('heading', { name: 'Vos droits' })).toBeVisible();
});

test('the terms page has real content', async ({ page }) => {
  await page.goto('/terms');

  await expect(page.getByRole('heading', { level: 1, name: /Conditions d.utilisation/ })).toBeVisible();
  await expect(page.getByRole('heading', { name: 'Objet et acceptation' })).toBeVisible();
  await expect(page.getByRole('heading', { name: 'Transactions et responsabilité' })).toBeVisible();
});
