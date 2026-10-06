# Browser compatibility — E2E

End-to-end suite for `front/` using **Playwright 1.63**, run against the real
dev stack (`make dev`, <https://localhost:8443>) with **no mocks**. It checks
that the app renders, routes and interacts the same way on the three browser
engines.

## Results

The suite has **41 tests across 12 spec files** (123 executions across the three
engines). Latest verified run:

| Engine   | Browser                                                          | Tests | Result                          |
| -------- | ---------------------------------------------------------------- | ----- | ------------------------------- |
| Chromium | Chrome for Testing 153.0.8010.12 (Playwright build `chromium-1243`) | 41    | ✅ 41 passed                     |
| Firefox  | Firefox 155.0 (Playwright build `firefox-1543`)                  | 41    | ✅ 41 passed                     |
| WebKit   | WebKit (Playwright build `webkit-2359`)                          | 40    | ✅ 40 passed (last run)          |

Chromium and Firefox pass with **`retries=0`** (no flaky test; the config keeps
`retries: 1` only as a safety net on slow hosts). WebKit runs inside Docker (see
below); its last verified run predates the 41st test, so re-run it to confirm 41
before the evaluation.

## How to run

The stack must be up first:

```bash
make dev
```

Then, from `front/` (the first two lines once):

```bash
npm ci                                           # dependencies, Playwright included
npx playwright install chromium firefox          # browser builds
npx playwright test                              # all projects
npx playwright test --project=chromium            # single engine
npx playwright test --project=chromium --project=firefox
npx playwright test --reporter=list               # console output
```

Chromium and Firefox run natively. **WebKit cannot run on this host** (missing
`libicu74` / `libjpeg-turbo8` and no `sudo`), so it runs inside the official
Playwright image:

```bash
cd front
docker build -f Dockerfile.e2e -t lb42-e2e .

# reuses the .auth/ forged on the host by a previous run
docker run --rm --network host \
  -v "$PWD/.auth":/work/.auth:z \
  -v "$PWD/playwright-report":/work/playwright-report:z \
  -e SKIP_GLOBAL_SETUP=1 \
  lb42-e2e npx playwright test --project=webkit --reporter=list
```

## Authentication in tests

A 42 OAuth login cannot be automated, and may not even be configured
(`secrets/FT_CLIENT_ID` / `FT_CLIENT_SECRET` empty: `/api/auth/login` answers
503). The seeded team accounts have no password either. To keep the suite
independent of the intra, `e2e/global.setup.ts` forges the `session` cookie for
each seeded role (`auth-password.spec.ts` creates its own email/password
accounts instead):

- reads `public_id` from the DB (`SELECT public_id FROM users WHERE email = …`),
- signs a HS256 JWT (`{ sub, iat, exp }`) with `secrets/SECRET_KEY`,
- writes `.auth/{admin,moderator,user,demo}.json`.

| State       | Account                     | Role      |
| ----------- | --------------------------- | --------- |
| `admin`     | `mzouhir@student.42.fr`     | admin     |
| `moderator` | `flomulle@student.42.fr`    | moderator |
| `user`      | `lmilando@student.42.fr`    | user      |
| `demo`      | `iargence@student.42.fr`    | admin     |

`.auth/` is git-ignored. Re-run any project to regenerate it; the Docker run
reuses the mounted files (`SKIP_GLOBAL_SETUP=1`).

## Coverage

41 tests in `front/e2e/`:

| Spec                  | Tests | What it covers                                                            |
| --------------------- | ----- | ------------------------------------------------------------------------- |
| `smoke.spec.ts`       | 8     | `/`, `/messages`, `/profile`, `/moderation`, `/analytics`, `/listings/create`, `/privacy`, `/terms` load with no JS error |
| `navigation.spec.ts`  | 4     | Nav items per role (admin/user/moderator) + mobile menu                    |
| `listings.spec.ts`    | 5     | Listing cards, search, URL location filter, filter modal, reset            |
| `listing-detail.spec.ts` | 3  | Open a listing, toggle favorite, report action                            |
| `listing-create.spec.ts` | 1  | Create a listing through the form                                          |
| `messages.spec.ts`    | 2     | Conversation list, open a conversation and send a message                  |
| `profile.spec.ts`     | 3     | Own profile tabs + edit modal, another user's friend/block actions         |
| `moderation.spec.ts`  | 2     | RBAC redirect for a plain user, every moderation tab for an admin          |
| `analytics.spec.ts`   | 2     | RBAC redirect for a plain user, dashboard + export action                  |
| `auth-password.spec.ts` | 7   | Email/password sign-up, wrong password, invalid fields caught before any API call, protected redirect then back, refused registration, hostile `next`, password change |
| `legal.spec.ts`       | 3     | Footer links to privacy/terms, real content on both pages                  |
| `multi-user.spec.ts`  | 1     | Two authenticated sessions coexist in separate contexts                    |

Tests run **serially** (`fullyParallel: false` + `workers: 1`) because they share
one database.

## Known issues / notes

- **Hydration races (test-side).** Several controls are client-only, so an
  interaction can no-op before React hydrates. The affected tests
  (`search updates the URL`, `filter modal opens`, `reset filters clears the
  query`, `opens the mobile menu`) use Playwright's `expect(...).toPass()` to
  retry the interaction. The `goto` helper waits on `getByRole('banner')`, since
  the global header is not always the only `<header>` on the page.
- **`useCurrentUser()` hang — fixed.** A guard could stay on “Chargement…” when
  one consumer won the `/users/me` race and another stayed loading. The
  module-level boolean cache was replaced with a shared in-flight promise
  (`src/hooks/useCurrentUser.ts`, commit `3de3dc9`), so every consumer resolves.
  The `moderation` tests no longer need a reload/retry workaround.
- **Test data accumulates.** The suite creates listings (`E2E Listing …`) and
  messages and has no teardown, so created rows are not cleaned up (there is no
  `DELETE /messages/{id}`).
- **Not covered** (out of the suite's scope): deleting listings or
  conversations, friend direct messages, unblock and the blocked list, and the
  realtime (WebSocket) features.

## Browser-specific limitations

- **Safari is tested through its engine, not the app.** The WebKit project runs
  Playwright's WebKit build on Linux, inside Docker. It shares Safari's
  rendering and JavaScript engine, but not the Safari application on macOS or
  iOS (its cookie and privacy policies, for example).
- **WebKit does not run natively on 42 computers**: its system libraries are
  missing and cannot be installed without `sudo`. Use the Docker image above.
- **Firefox keeps its own certificate store.** Trusting the self-signed
  development certificate in the operating system does not silence Firefox's
  warning: accept the certificate in Firefox itself, or import it there. Every
  browser asks once for the certificate.
- **Firefox console on Grafana's pages** (`/grafana/`, not the application)
  shows two fingerprinting-protection warnings from Grafana's bundled
  FingerprintJS. They come from Firefox and break nothing. See the
  [monitoring README](../monitoring/README.md#troubleshooting).
