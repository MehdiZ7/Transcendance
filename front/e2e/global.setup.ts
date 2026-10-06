import { readFileSync, mkdirSync, writeFileSync } from 'fs';
import { execSync } from 'child_process';
import path from 'path';
import jwt from 'jsonwebtoken';

// Repo root is two levels up from this file (front/e2e/global.setup.ts).
const REPO_ROOT = path.resolve(__dirname, '..', '..');
// Playwright resolves `storageState: '.auth/xxx.json'` relative to the config
// dir (front/), so we write the session files there.
const AUTH_DIR = path.resolve(__dirname, '..', '.auth');
const SECRET_FILE = path.join(REPO_ROOT, 'secrets', 'SECRET_KEY');
const POSTGRES_USER_FILE = path.join(REPO_ROOT, 'secrets', 'POSTGRES_USER');

/**
 * Read a seeded user's public_id straight from the dev database.
 * Uses `docker compose exec` (the dev stack must be running: `make dev`).
 */
function publicIdFor(email: string): string {
  const dbUser = readFileSync(POSTGRES_USER_FILE, 'utf-8').trim();
  const out = execSync(
    `docker compose -f docker-compose.yml -f docker-compose.dev.yml exec -T db ` +
      `psql -U ${dbUser} -d lb42db -t -A ` +
      `-c "SELECT public_id FROM users WHERE email='${email}' LIMIT 1;"`,
    { cwd: REPO_ROOT },
  )
    .toString()
    .trim();

  if (!out) throw new Error(`E2E setup: no user found for ${email}`);
  return out;
}

function storageStateFor(email: string, secret: string) {
  const token = jwt.sign({ sub: publicIdFor(email) }, secret, {
    algorithm: 'HS256',
    expiresIn: '7d',
  });

  return {
    cookies: [
      {
        name: 'session',
        value: token,
        domain: 'localhost',
        path: '/',
        httpOnly: true,
        secure: true,
        sameSite: 'Lax' as const,
        expires: Math.floor(Date.now() / 1000) + 7 * 86400,
      },
    ],
    origins: [] as { origin: string; localStorage: { name: string; value: string }[] }[],
  };
}

/**
 * Playwright global setup: forge a session cookie for each seeded role so the
 * tests can authenticate against the real backend (42 OAuth cannot be
 * automated). Set SKIP_GLOBAL_SETUP=1 to reuse already-generated `.auth` files
 * (used by the WebKit Docker run, which has no docker/secrets access).
 */
export default function globalSetup(): void {
  if (process.env.SKIP_GLOBAL_SETUP === '1') return;

  const secret = readFileSync(SECRET_FILE, 'utf-8').trim();
  mkdirSync(AUTH_DIR, { recursive: true });

  const accounts: Record<string, string> = {
    admin: 'mzouhir@student.42.fr',
    moderator: 'flomulle@student.42.fr',
    user: 'lmilando@student.42.fr',
    demo: 'iargence@student.42.fr',
  };

  for (const [name, email] of Object.entries(accounts)) {
    writeFileSync(
      path.join(AUTH_DIR, `${name}.json`),
      JSON.stringify(storageStateFor(email, secret)),
    );
  }
}
