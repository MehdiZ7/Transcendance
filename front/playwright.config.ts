import { defineConfig, devices } from '@playwright/test';

export default defineConfig({
  testDir: './e2e',
  fullyParallel: false,          // base partagée → fiable
  workers: 1,                    // un seul fichier à la fois (base partagée)
  timeout: 60_000,
  expect: { timeout: 10_000 },
  retries: 1,                    // filet de sécurité (races d'hydratation résiduelles)
  reporter: 'html',
  globalSetup: './e2e/global.setup.ts',
  use: {
    baseURL: process.env.PLAYWRIGHT_BASE_URL ?? 'https://localhost:8443',
    ignoreHTTPSErrors: true,
    trace: 'on-first-retry',
    actionTimeout: 15_000,
    navigationTimeout: 30_000,
  },
  projects: [
    { name: 'chromium', use: { ...devices['Desktop Chrome'], storageState: '.auth/admin.json' } },
    { name: 'firefox',  use: { ...devices['Desktop Firefox'], storageState: '.auth/admin.json' } },
    { name: 'webkit',   use: { ...devices['Desktop Safari'], storageState: '.auth/admin.json' } },
  ],
});
