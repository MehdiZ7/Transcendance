import { test, expect } from './helpers';

// These flows start logged out, so clear the session storage from the config.
test.use({ storageState: { cookies: [], origins: [] } });

test.describe('auth email/password', () => {
  test('registers a new account', async ({ page }) => {
    const email = `e2e-${Date.now()}@example.com`;
    const password = 'Password123!';

    await page.goto('/');
    await page.getByRole('button', { name: 'Connexion', exact: true }).first().click();
    await page.getByRole('button', { name: 'Inscription' }).click();

    await page.getByLabel('Nom affiché').fill('E2E User');
    await page.getByLabel('Email').fill(email);
    await page.getByLabel('Mot de passe', { exact: true }).fill(password);
    await page.getByLabel('Confirmer le mot de passe').fill(password);
    await page.getByRole('button', { name: 'Créer mon compte' }).click();

    await expect(page.getByRole('button', { name: 'Déconnexion' })).toBeVisible({ timeout: 20_000 });
  });

  test('shows an error on a wrong password', async ({ page, allowConsole }) => {
    // Chrome logs the refused login itself; the form handles it
    allowConsole(/status of 401/);
    await page.goto('/');
    await page.getByRole('button', { name: 'Connexion', exact: true }).first().click();

    // unique: a fixed address would reach its per-email limit (10 an hour)
    await page.getByLabel('Email').fill(`does-not-exist-${Date.now()}@example.com`);
    await page.getByLabel('Mot de passe', { exact: true }).fill('wrong-password');
    await page.getByRole('button', { name: 'Se connecter', exact: true }).click();

    // filtered: Next's route announcer is a role=alert too
    await expect(page.getByRole('alert').filter({ hasText: 'Email ou mot de passe incorrect' })).toBeVisible();
  });

  test('flags invalid fields without calling the API', async ({ page }) => {
    const authCalls: string[] = [];
    page.on('request', (r) => {
      if (/\/api\/auth\/(login|register)$/.test(r.url())) authCalls.push(r.url());
    });
    await page.goto('/');
    await page.getByRole('button', { name: 'Connexion', exact: true }).first().click();

    // login checks the format too: a malformed address costs no auth request
    const email = page.getByLabel('Email');
    await email.fill('not-an-email');
    await page.getByLabel('Mot de passe', { exact: true }).fill('whatever');
    await page.getByRole('button', { name: 'Se connecter', exact: true }).click();
    await expect(email).toBeFocused();
    await expect(email).toHaveAttribute('aria-invalid', 'true');
    await expect(email).toHaveAccessibleDescription("Format d'adresse email invalide.");
    await email.fill('x@example.com');
    await expect(email).not.toHaveAttribute('aria-invalid');

    // the focus goes to the first invalid field, in form order
    await page.getByRole('button', { name: 'Inscription' }).click();
    await page.getByLabel('Mot de passe', { exact: true }).fill('short');
    await page.getByRole('button', { name: 'Créer mon compte' }).click();
    await expect(page.getByLabel('Nom affiché')).toBeFocused();
    await expect(page.getByLabel('Nom affiché')).toHaveAccessibleDescription('Le nom affiché est requis.');
    await expect(page.getByLabel('Mot de passe', { exact: true })).toHaveAccessibleDescription(/au moins 8 caractères/);
    await expect(page.getByLabel('Confirmer le mot de passe')).toHaveAttribute('aria-invalid', 'true');
    expect(authCalls).toEqual([]);
  });

  test('a protected page sends a logged-out visitor to /login, then back', async ({ page }) => {
    const email = `e2e-next-${Date.now()}@example.com`;
    const password = 'Password123!';

    await page.goto('/messages');
    await expect(page).toHaveURL(/\/login\?next=%2Fmessages$/);

    await page.getByRole('button', { name: 'Inscription' }).click();
    await page.getByLabel('Nom affiché').fill('E2E Next');
    await page.getByLabel('Email').fill(email);
    await page.getByLabel('Mot de passe', { exact: true }).fill(password);
    await page.getByLabel('Confirmer le mot de passe').fill(password);
    await page.getByRole('button', { name: 'Créer mon compte' }).click();

    await expect(page).toHaveURL(/\/messages$/, { timeout: 20_000 });
  });

  test('explains why a registration is refused', async ({ page, allowConsole }) => {
    // 403 (42 address) and 409 (address taken), logged by Chrome, handled by the form
    allowConsole(/status of 40[39]/);
    const taken = `e2e-taken-${Date.now()}@example.com`;
    const created = await page.request.post('/api/auth/register', {
      data: { email: taken, password: 'Password123!', display_name: 'Taken' },
    });
    expect(created.status()).toBe(201);
    await page.context().clearCookies();

    await page.goto('/');
    await page.getByRole('button', { name: 'Connexion', exact: true }).first().click();
    await page.getByRole('button', { name: 'Inscription' }).click();
    const submit = async (email: string) => {
      await page.getByLabel('Nom affiché').fill('E2E User');
      await page.getByLabel('Email').fill(email);
      await page.getByLabel('Mot de passe', { exact: true }).fill('Password123!');
      await page.getByLabel('Confirmer le mot de passe').fill('Password123!');
      await page.getByRole('button', { name: 'Créer mon compte' }).click();
    };
    const alert = page.locator('p[role="alert"]');

    await submit(`e2e-${Date.now()}@student.42.fr`);
    await expect(alert).toContainText('Se connecter avec 42');
    await submit(taken.toUpperCase());
    await expect(alert).toContainText('Un compte existe déjà');
  });

  test('ignores a next that leaves the site', async ({ page }) => {
    await page.goto(`/login?next=${encodeURIComponent('//evil.example/x')}`);
    await page.getByRole('button', { name: 'Inscription' }).click();
    await page.getByLabel('Nom affiché').fill('E2E Next');
    await page.getByLabel('Email').fill(`e2e-evil-${Date.now()}@example.com`);
    await page.getByLabel('Mot de passe', { exact: true }).fill('Password123!');
    await page.getByLabel('Confirmer le mot de passe').fill('Password123!');
    await page.getByRole('button', { name: 'Créer mon compte' }).click();

    await expect(page.getByRole('button', { name: 'Déconnexion' })).toBeVisible({ timeout: 20_000 });
    expect(new URL(page.url()).pathname).toBe('/');
  });

  test('changes the password from the profile', async ({ page }) => {
    const email = `e2e-change-${Date.now()}@example.com`;
    const created = await page.request.post('/api/auth/register', {
      data: { email, password: 'Password123!', display_name: 'E2E Change' },
    });
    expect(created.status()).toBe(201);

    await page.goto('/profile');
    await page.getByRole('button', { name: /Éditer le profil/ }).click();
    // the edit modal is taller than a laptop screen: its password section must
    // still be reachable (the modal scrolls)
    await page.getByLabel('Mot de passe actuel').fill('Password123!');
    await page.getByLabel('Nouveau mot de passe', { exact: true }).fill('NewPassword456!');
    await page.getByLabel('Confirmer le nouveau mot de passe').fill('NewPassword456!');
    await page.getByRole('button', { name: 'Enregistrer le mot de passe' }).click();
    await expect(page.getByText('Mot de passe mis à jour.')).toBeVisible();

    const login = await page.request.post('/api/auth/login', {
      data: { email, password: 'NewPassword456!' },
    });
    expect(login.status()).toBe(200);
  });
});
