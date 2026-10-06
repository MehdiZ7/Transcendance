import { test, expect, AUTH, expectCleanConsole, watchConsole } from './helpers';

const BASE_URL = process.env.PLAYWRIGHT_BASE_URL ?? 'https://localhost:8443';

/**
 * Two authenticated sessions can coexist in the same run (independent browser
 * contexts). This is the foundation for exercising multi-user flows.
 */
test('two sessions coexist', async ({ browser, browserName }) => {
  const adminContext = await browser.newContext({
    storageState: AUTH.admin,
    baseURL: BASE_URL,
    ignoreHTTPSErrors: true,
  });
  const userContext = await browser.newContext({
    storageState: AUTH.user,
    baseURL: BASE_URL,
    ignoreHTTPSErrors: true,
  });

  // these contexts are not the test's own: watch their console here
  const problems = watchConsole(adminContext);
  watchConsole(userContext, problems);

  const adminPage = await adminContext.newPage();
  const userPage = await userContext.newPage();

  await adminPage.goto('/profile');
  await userPage.goto('/profile');

  await expect(adminPage.locator('header')).toBeVisible();
  await expect(userPage.locator('header')).toBeVisible();

  // The two contexts must not share identity.
  const adminName = await adminPage.locator('header').innerText();
  const userName = await userPage.locator('header').innerText();
  expect(adminName).not.toBe(userName);

  await adminContext.close();
  await userContext.close();
  expectCleanConsole(problems, browserName);
});
