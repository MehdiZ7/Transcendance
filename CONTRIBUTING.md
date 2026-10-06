# Contributing Guide — Le Bon 42

This document describes the development workflow for the team: commit conventions, branching strategy, the checks to run before a pull request, and the API conventions. Everyone on the team should follow these rules to keep the project consistent and easy to review.

How to run, configure and test each part in detail is in its own README: [`backend/README.md`](backend/README.md), [`front/README.md`](front/README.md), [`nginx/README.md`](nginx/README.md), [`monitoring/README.md`](monitoring/README.md).

## 1. Commit Messages

We use [Conventional Commits](https://www.conventionalcommits.org/).

```
<type>(<scope>): <short imperative description>

[optional body]

[optional footer]
```

### Types

| Type       | When to use it                                  |
|------------|--------------------------------------------------|
| `feat`     | new feature                                       |
| `fix`      | bug fix                                           |
| `refactor` | code change with no behavior change               |
| `test`     | adding or updating tests                          |
| `docs`     | documentation only                                |
| `chore`    | tooling, dependencies, config                     |
| `style`    | formatting only (no logic change)                 |
| `perf`     | performance improvement                           |

### Scopes

The part of the project the change touches, for example:

- back end: `auth`, `listings`, `messages`, `profile`, `moderation`, `analytics`, `uploads`, `quotas`, `realtime`, `db`, `seed`;
- front: `front`, or the feature (`front messages`, `authform`…);
- infrastructure: `infra`, `make`, `nginx`, `grafana`, `prometheus`.

### Rules

- Description in lowercase, imperative mood.
- One commit = one logical change. Avoid large, unrelated bundles.
- Use the body to explain **why**, not **what** (the diff already shows what changed).

### Examples

```
feat(auth): email/password sign-up, login and password change
fix(listings): fix price filter on search page
feat(uploads): re-encode images with Pillow, strip EXIF and validate content
fix(prometheus): not reachable except for grafana and backend
docs(realtime): document friend_message.created and friend_typing
```

## 2. Branching Strategy

The repository has two permanent, protected branches (`main`, `dev`) and two long-lived integration branches (`backend`, `front`) that are not protected, to allow fast day-to-day work.

```
main                                    <- protected, PR + review required
 └── dev                                <- protected, PR + review required
      ├── backend
      │    ├── feature/auth
      │    ├── feature/limits-and-quotas
      │    └── ...
      └── front
           ├── feature/listings
           ├── mobile-messages-interface
           └── ...
```

### Rules

- `main` and `dev` are protected: no direct push, a pull request and a review are required.
- `backend` and `front` accept direct pushes. Keep pushes small and working.
- Task branches are created from an up-to-date `backend`, `front` or `dev`, never directly from `main`.
- Branch naming: the task name, in lowercase, words separated by hyphens, optionally prefixed with `feature/` or `fix/`.
  - `feature/limits-and-quotas`
  - `fix/grafana-console-errors`
  - `mobile-messages-interface`
- PR **`backend`/`front` → `dev`**: review by at least one teammate, especially if it touches the API contract between front and back.
- PR **`dev` → `main`**: strictest gate, review required. This is what ships for the defense. There is no CI pipeline: the reviewer runs the checks of §3 locally before approving.

## 3. Checks Before a Pull Request

From the repository root, with Docker (or Podman) and [uv](https://docs.astral.sh/uv/) installed:

| Command | What it checks |
|---|---|
| `make test` | Applies every migration to a throwaway PostgreSQL 18, then runs the whole back-end suite (`pytest`) |
| `cd backend && uv run ruff check src tests` | Back-end lint |
| `cd backend && uv run mypy src` | Back-end type checks |
| `cd front && npm run lint` | Front lint (ESLint) |
| `cd front && npx playwright test` | Browser tests on Chromium, Firefox and WebKit, against a running `make dev` (see [`front/BROWSERS.md`](front/BROWSERS.md)) |

Run the back-end checks before **every push** to `backend`: nothing else stands between that branch and a `→ dev` pull request.

### Changing the database schema

1. Edit the models in `backend/src/app/models/`.
2. Generate a migration: `uv run alembic revision --autogenerate -m "..."`, from `backend/`, against a database at `head`.
3. **Review the generated file**: autogenerate misses extensions, triggers, data and some constraint changes.
4. Run `make test`, which applies every migration to an empty database.

Details: [Migrations](backend/README.md#migrations) in the back-end README.

## 4. Back-end Tests

The suite lives in `backend/tests/`; how it is built is described in [Testing](backend/README.md#testing). The rules for new tests:

1. **Real PostgreSQL, never SQLite.** The schema relies on `JSONB`, `CITEXT`, `gen_random_uuid()`, a `tsvector` trigger and row locks. `make test` provides a disposable database; never point tests at the dev or production database.
2. **Isolation.** Each test runs in a transaction that is rolled back afterwards (`tests/conftest.py`), so tests stay independent without re-running migrations.
3. **Reusable fixtures** (`client`, `db_session`, `create_user`, `create_listing`, `login_as`…) instead of duplicating setup in every test.
4. **Independent tests**: each test can run alone, in any order.
5. **Naming convention**: `test_<action>_<condition>_<expected_result>`, e.g. `test_create_listing_without_auth_returns_401`.
6. **Cover at minimum**: the happy path, validation errors (`422`), authorization cases (`401`, `403`, `404`), and every limit or quota the route enforces.

## 5. API Conventions

`/api/v1/<resource>`, plural, lowercase, English (`/listings`, `/conversations`, `/reports`). The full reference is the [Endpoint reference](backend/README.md#endpoint-reference).

- **IDs**: users and listings are addressed by `public_id` (a UUID — never the internal bigint `id`, which is enumerable): `/listings/{public_id}`, `/users/{public_id}`. Every other resource uses its integer `id`.
- **Nesting**: at most two levels, only when owned by the parent: `/conversations/{id}/messages`, `/users/{public_id}/listings`, `/friends/{public_id}/messages`.
- **Methods**: `GET` read, `POST` create or action (`/mark-sold`, `/accept`, `/resolve`), `PATCH` partial update (no `PUT`), `DELETE` remove.
- **Deletion**: a seller's `DELETE /listings/{public_id}` and an author's `DELETE /reviews/{id}` are soft (`deleted_at`). Moderation removes listings, messages, reviews and users softly, so it can be undone. An admin's `DELETE /users/{public_id}` is a real delete; friendships, favorites and blocks are deleted for real too.
- **Query params**: snake_case (`before_id`, `target_type`…), with two exceptions kept from the original contract with the front: the listing filters `categorie`, `prix_min`, `prix_max` (beside `q`, `location` and `sort`), and the analytics dates `startDate` / `endDate`. Check `front/src/types/*.ts` and `front/src/lib/api/*.ts` before adding one.
- **Response**: the resource or array directly, no envelope. Paginated lists are `{data, total, page, limit, total_pages}`. JSON fields are snake_case, with no camelCase layer.
- **Auth**: its own namespace, outside `/api/v1`: `/api/auth/login` (42), `/api/auth/callback`, `/api/auth/logout`, `/api/auth/register`, `/api/auth/login` (`POST`, email/password), `/api/auth/password`.
