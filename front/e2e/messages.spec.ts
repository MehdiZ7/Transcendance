import { test, expect, goto, AUTH } from './helpers';

test.describe('messages', () => {
  // The demo account owns the seeded conversations.
  test.use({ storageState: AUTH.demo });

  test('lists conversations', async ({ page }) => {
    await goto(page, '/messages');
    await expect(page.locator('aside button').first()).toBeVisible({ timeout: 20_000 });
  });

  test('opens a conversation and sends a message', async ({ page }) => {
    await goto(page, '/messages');

    await page.locator('aside button').first().click();

    const input = page.getByPlaceholder('Écrivez votre message...');
    await expect(input).toBeVisible({ timeout: 20_000 });

    const body = `E2E message ${Date.now()}`;
    await input.fill(body);
    await page.getByRole('button', { name: 'Envoyer' }).click();

    // The text appears both in the conversation preview and the bubble.
    await expect(page.getByText(body).last()).toBeVisible({ timeout: 20_000 });
  });
});
