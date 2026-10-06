# lb42 — Backend API

The HTTP and real-time API behind **Le Bon 42**, the classifieds platform for
the 42 campus. It serves listings, buyer–seller conversations, friends and
direct messages, reviews, moderation, personal statistics and the admin
analytics dashboard. Signing in goes through **42 OAuth2** or an email/password
account.

This document is the single reference for the backend: how to run and
configure it, how to call it, the rules it enforces, and how to extend it.

| Related topic | Document |
|---|---|
| Project overview | [`../README.md`](../README.md) |
| Team workflow (commits, branches, reviews) | [`../CONTRIBUTING.md`](../CONTRIBUTING.md) |
| Database diagram, SSE sequence diagram | [`../schema_design.md`](../schema_design.md) |
| Real-time core (wire protocol, delivery guarantees, close codes) | [`src/app/core/realtime/README.md`](src/app/core/realtime/README.md) |
| Real-time client (front side) | [`../front/src/lib/realtime/README.md`](../front/src/lib/realtime/README.md) |

## Contents

- **Get started**
  - [Quick start](#quick-start)
  - [Find your way](#find-your-way)
  - [Overview](#overview)
  - [Running the API](#running-the-api)
  - [Configuration](#configuration)
- **Use the API**
  - [API conventions](#api-conventions)
  - [Authentication (42 OAuth2)](#authentication-42-oauth2)
  - [Authorization](#authorization)
  - [Endpoint reference](#endpoint-reference)
  - [Real-time](#real-time)
- **Rules the API enforces**
  - [Business rules](#business-rules)
  - [Limits, quotas and rate limiting](#limits-quotas-and-rate-limiting)
- **Build and operate**
  - [Database](#database)
  - [Developer guide](#developer-guide)
  - [Testing](#testing)
  - [Observability](#observability)
  - [Security summary](#security-summary)
  - [Deployment checklist](#deployment-checklist)
- **Help**
  - [Troubleshooting](#troubleshooting)
  - [Known limitations](#known-limitations)
  - [Glossary](#glossary)

---

## Quick start

**Prerequisites:** Docker with the Compose plugin (or rootless Podman with
podman-compose), GNU make and openssl. Running the tests or the API outside
Docker also needs [uv](https://docs.astral.sh/uv/).

1. **Start the stack** from the repository root:

   ```bash
   make dev
   ```

   On the first run, `make` creates `.env` and the files under `secrets/`, and
   asks for the two 42 OAuth credentials. You can press Enter to skip them:
   everything works except signing in.

2. **Check that the API answers:**

   ```bash
   curl -k https://localhost:8443/api/v1/health
   # {"status":"ok"}
   ```

   `-k` is needed because the development certificate is self-signed. In a
   browser, accept the certificate warning once.

3. **Explore it:** open <https://localhost:8443/api/v1/docs> (Swagger UI).
   The database is pre-filled with demo listings, users and conversations.

4. **Enable sign-in:** register an application on the 42 intra and paste its
   credentials, as described in
   [Registering the application](#registering-the-application). Then sign in
   at <https://localhost:8443/api/auth/login>.

Stop the stack with `Ctrl+C`, or `make down` from another terminal.

> [!TIP]
> A bare `make` is the same as `make up`: it starts the stack in the
> background, with the production images. Use `make dev` while developing.

## Find your way

| I want to… | Read |
|---|---|
| Run the backend for the first time | [Quick start](#quick-start), then [Running the API](#running-the-api) |
| Call the API from the front | [API conventions](#api-conventions), [Endpoint reference](#endpoint-reference), [Real-time](#real-time) |
| Try requests by hand | [Try it with curl](#try-it-with-curl) |
| Understand the login, or fix a failing one | [Authentication](#authentication-42-oauth2), [Troubleshooting](#troubleshooting) |
| Know who may do what | [Authorization](#authorization), [Business rules](#business-rules) |
| Add or change an endpoint | [Developer guide](#developer-guide) |
| Change the database schema | [Migrations](#migrations) |
| Relax a limit for a demo | [Limits, quotas and rate limiting](#limits-quotas-and-rate-limiting) |
| Deploy on a real host | [Deployment checklist](#deployment-checklist) |
| Run the tests | [Testing](#testing) |

---

## Overview

### Technology

| Concern | Choice |
|---|---|
| Language and packaging | Python 3.14, managed with [uv](https://docs.astral.sh/uv/) (`uv.lock` pins every dependency) |
| Web framework | FastAPI, served by Uvicorn |
| Data access | SQLAlchemy 2 (async ORM) over asyncpg |
| Schema migrations | Alembic |
| Database | PostgreSQL 18 (`pgcrypto`, `citext`, `JSONB`, `tsvector`) |
| Validation and settings | Pydantic 2, pydantic-settings |
| Sessions | HS256 JWT (PyJWT) in an HttpOnly cookie |
| Outbound HTTP to the 42 intra | httpx |
| Metrics | prometheus-fastapi-instrumentator |
| Development tools | pytest, pytest-asyncio, pytest-cov, ruff, mypy |

### Architecture

The API runs behind nginx, on the same origin as the Next.js front. Cookies are
therefore first-party, and CORS is not needed.

```
browser ──HTTPS──▶ nginx (TLS, per-IP rate limits, security headers)
                     ├── /api/ws      ──▶ api:8000   WebSocket (real-time)
                     ├── /api/v1/uploads/ ──▶ api:8000   image uploads (6 MB body cap)
                     ├── /api/auth/   ──▶ api:8000   42 login, callback, logout, email/password
                     ├── /api/        ──▶ api:8000   REST API (/api/v1), OpenAPI
                     ├── /media/      ──▶ media volume (static files)
                     ├── /grafana/    ──▶ grafana:3000
                     └── /            ──▶ web:3000   Next.js front

web:3000   ──server-side fetch──▶ api:8000/api/v1    (internal network, bypasses nginx)
api:8000   ──asyncpg──────────────▶ db:5432             (PostgreSQL 18)
prometheus ──scrape───────────────▶ api:8000/metrics, postgres-exporter:9187
grafana    ──PromQL───────────────▶ prometheus:9090     (internal only, not routed by nginx)
```

> [!IMPORTANT]
> The API runs as a **single Uvicorn worker**. Rate-limit counters, the
> real-time hub, the analytics event bus and the presence tracker all live in
> process memory. See [Known limitations](#known-limitations).

### Service URLs

With `make dev` or `make up` and the default `.env`:

| URL | Purpose |
|---|---|
| `https://localhost:8443/` | The front (Next.js) |
| `https://localhost:8443/api/v1/…` | REST API |
| `https://localhost:8443/api/auth/login` | Start the 42 login |
| `wss://localhost:8443/api/ws` | Real-time WebSocket |
| `https://localhost:8443/api/v1/docs` | Swagger UI (see the note below) |
| `https://localhost:8443/api/openapi.json` | OpenAPI 3 schema |
| `https://localhost:8443/grafana/` | Grafana dashboards. Prometheus has no URL: query it from Grafana's *Explore* |
| `127.0.0.1:5432` | PostgreSQL, **`make dev` only** |

- **Swagger UI** loads its scripts and styles from `cdn.jsdelivr.net`. That
  works under `make dev`. Under `make up`, the production
  Content-Security-Policy blocks them and the page stays blank: use
  `/api/openapi.json` with any OpenAPI client instead.
- **Not in the OpenAPI schema:** the WebSocket and the admin SSE stream. They
  are documented in [Real-time](#real-time).
- **Without Docker** (bare Uvicorn), the same paths are served on
  `http://localhost:8000`, for example `http://localhost:8000/api/v1/docs`.

### Project layout

```
backend/
├── Dockerfile               multi-stage image: builder (uv sync --frozen), runtime, dev
├── entrypoint.sh            container start: secrets → migrations → optional seed → uvicorn
├── pyproject.toml, uv.lock  dependencies, pytest and ruff configuration
├── alembic.ini
├── migrations/
│   ├── env.py               async Alembic environment; URL built from the POSTGRES_* settings
│   └── versions/            the initial migration (bfa429204c94)
├── src/app/
│   ├── main.py              FastAPI app: lifespan, routers, CORS, /metrics
│   ├── api/
│   │   ├── auth.py          /api/auth/*   42 OAuth login, callback, logout; email/password register, login, password
│   │   ├── ws.py            /api/ws       real-time WebSocket endpoint
│   │   └── v1/              /api/v1/*     one module per resource, wired in v1/__init__.py
│   ├── core/
│   │   ├── config.py        typed settings, *_FILE secret expansion
│   │   ├── db.py            async engine, session factory, get_session
│   │   ├── security.py      session JWT, cookies, authentication and role dependencies
│   │   ├── oauth42.py       42 intra client (code exchange, profile)
│   │   ├── passwords.py     argon2id hashing and verification, off the event loop
│   │   ├── quotas.py        per-user row quotas
│   │   ├── ratelimit.py     per-user REST rate limits
│   │   ├── presence.py      last-seen tracker for the analytics "online" count
│   │   ├── analytics_bus.py in-memory fan-out to the admin SSE streams
│   │   ├── listing_filters.py  shared definition of the listing "stock"
│   │   ├── serializers.py   ORM → response-model helpers
│   │   ├── uploads.py       image storage, re-encoding, allowed image references, orphan purge
│   │   └── realtime/        generic WebSocket pub/sub core (has its own README)
│   ├── realtime.py          the application's single real-time router and hub
│   ├── realtime_topics.py   application topics (user:<id>, presence) and typing relays
│   ├── models/              SQLAlchemy declarative models
│   ├── schemas/             Pydantic request/response models; limits.py holds input limits
│   └── seeds.py             demo data (development only)
└── tests/
    ├── conftest.py          fixtures: transactional session, HTTP client, factories, login_as
    ├── test_*.py            API tests, one file per module
    ├── test_ws/             real-time core tests (no database needed)
    ├── test_auth/           curl tests against the running stack (make test_auth)
    └── live/realtime/       manual browser bench for the real-time core
```

---

## Running the API

### With the full stack (recommended)

Run these from the repository root:

| Command | Effect |
|---|---|
| `make dev` | Build and start every service in the foreground, with the development overrides. `Ctrl+C` stops it |
| `make up` (or a bare `make`) | Build and start every service in the background, with the production images and nginx configuration |
| `make down` | Stop the stack. Volumes (database, media) are kept |
| `make clean` | Stop the stack and delete its volumes, **database included** |
| `make fclean` | `clean`, then remove the locally built images |
| `make re` | `fclean`, then `up` |
| `make ps`, `make logs` | List containers, follow logs |
| `make seed_dev`, `make seed_prod` | Re-run the demo seed in the running `api` container, under `make dev` or `make up` |

> [!WARNING]
> `make clean`, `make fclean` and `make re` delete the PostgreSQL volume. Use
> `make down` to stop the stack and keep your data.

**First run.** `make` creates `.env` from `.env.example` and the files under
`secrets/`:

- it writes the database user, and generates the database password and
  `SECRET_KEY`;
- it prompts for the two 42 credentials. They can be left empty: login then
  answers `503` until they are filled in.

**Development overrides.** `make dev` layers
[`../docker-compose.dev.yml`](../docker-compose.dev.yml) on top of the base
file. For the API this means:

- `backend/src` is bind-mounted read-only and Uvicorn runs with `--reload`:
  saving a Python file restarts the API;
- `SQL_ECHO=true` logs every SQL statement;
- `SEED_DEMO_DATA=true` loads demo data on first start;
- PostgreSQL is published on `127.0.0.1:5432` for local tools;
- the container runs with your host UID/GID, so the mounted files are
  readable (it falls back to 1001 outside the 1000–60000 range, which rootless
  Podman cannot map);
- nginx uses its development configuration, which has no CSP and no gzip.

**`make up` and `ENVIRONMENT`.** `make up` uses production images and the
production nginx configuration, but the application setting `ENVIRONMENT`
still defaults to `dev` unless `.env` sets it. See the
[Deployment checklist](#deployment-checklist).

### Container start sequence

[`entrypoint.sh`](entrypoint.sh) runs these steps in order:

1. **Secrets.** Each `<NAME>_FILE` variable is replaced by `<NAME>`, holding
   the file's content. Compose mounts the secrets at `/run/secrets/<NAME>`. If
   a file cannot be read, the container stops.
2. **Media.** It checks that `/srv/media` is writable. That volume is shared
   with nginx, which serves it under `/media/`.
3. **Migrations.** It runs `alembic upgrade head`, so migrations are applied
   on every start.
4. **Seed.** It runs `python -m app.seeds` when `SEED_DEMO_DATA=true`.
5. **Server.** It starts Uvicorn on `0.0.0.0:8000`: with `--reload` in
   development, otherwise with `--workers ${UVICORN_WORKERS:-1}`. In both
   cases it passes `--ws-max-size ${WS_MAX_FRAME_BYTES:-4096}`.

The Compose healthcheck polls `GET /api/v1/health`. nginx starts only once the
API reports healthy.

### Without Docker

This needs uv and a reachable PostgreSQL. The simplest option is the dev
stack's database, which `make dev` publishes on `127.0.0.1:5432`:

```bash
cd backend
uv sync                      # creates .venv; installs the app and the dev tools
export POSTGRES_HOST=127.0.0.1 \
       POSTGRES_USER_FILE=../secrets/POSTGRES_USER \
       POSTGRES_PASSWORD_FILE=../secrets/POSTGRES_PASSWORD \
       FT_CLIENT_ID_FILE=../secrets/FT_CLIENT_ID \
       FT_CLIENT_SECRET_FILE=../secrets/FT_CLIENT_SECRET \
       FT_REDIRECT_URI=http://localhost:8000/api/auth/callback \
       COOKIE_SECURE=false
uv run alembic upgrade head
uv run uvicorn app.main:app --reload --port 8000
```

- **Secrets.** The app resolves the `*_FILE` variables itself
  (`expand_file_secrets` in `core/config.py`), with the same convention as the
  container. An explicit `NAME` takes precedence over `NAME_FILE`.
- **Plain HTTP.** `COOKIE_SECURE=false` is needed because this serves plain
  HTTP. The redirect URI must also be registered on the intra (see
  [Registering the application](#registering-the-application)).
- **Session key.** Without `SECRET_KEY`, the app generates a random key per
  process, so sessions do not survive a restart. That is acceptable in
  development and refused when `ENVIRONMENT=prod`. Add
  `SECRET_KEY_FILE=../secrets/SECRET_KEY` to keep sessions across restarts.
- **Another front origin.** To use this API from a front served elsewhere,
  such as `next dev` on `http://localhost:3000`, set `CORS_ORIGINS` and
  `WS_ALLOWED_ORIGINS` to that origin.

---

## Configuration

### How settings are loaded

- [`core/config.py`](src/app/core/config.py) defines a single typed `Settings`
  object, built once at import. A missing or malformed value fails at
  startup, not halfway through a request.
- Sources, highest priority first:
  1. environment variables (case-insensitive);
  2. a `.env` file in the working directory;
  3. the defaults in the code.
- Secrets follow the `<NAME>_FILE` convention: the variable holds a path, and
  the file's content becomes the value.
- The database URL is never configured directly. It is composed from the
  `POSTGRES_*` settings, with the user and password URL-encoded, and only a
  masked form ever reaches the logs.

> [!IMPORTANT]
> **Under Docker Compose**, the `api` container receives only the variables
> listed in its `environment:` block in
> [`../docker-compose.yml`](../docker-compose.yml) and the dev override. The
> repository `.env` fills in the Compose file; it is **not** passed to the
> container as a whole. To change another setting in Docker (a quota, a rate
> limit, a WebSocket limit), add it to that block.

### Secrets

These are files under `secrets/` at the repository root, which is git-ignored.
They are mounted as Docker secrets and passed to the app as `<NAME>_FILE`.

| Secret | Created by `make` | Purpose |
|---|---|---|
| `POSTGRES_USER` | written as `lb42` | Database role |
| `POSTGRES_PASSWORD` | random, 48 hex characters | Database password |
| `SECRET_KEY` | random, 64 hex characters | Signs the session JWT. Rotating it logs everyone out |
| `FT_CLIENT_ID` | prompted, may stay empty | UID of the intra OAuth application |
| `FT_CLIENT_SECRET` | prompted, may stay empty | Secret of the intra OAuth application |
| `GRAFANA_USER` | written as `lb42` | Grafana administrator. Not read by the API |
| `GRAFANA_PASSWORD` | random, 48 hex characters | Grafana administrator's password. Not read by the API |

An empty `FT_*` file counts as missing: the next `make dev` or `make up`
prompts for it again.

### Application settings

| Variable | Default | Notes |
|---|---|---|
| `ENVIRONMENT` | `dev` | `dev` or `prod`. `prod` makes a missing `SECRET_KEY` fatal |
| `SQL_ECHO` | `false` | Log every SQL statement (`true` under `make dev`) |
| `SERVER_NAME` | `localhost` | Public host name. Used to derive the allowed WebSocket origin |
| `HTTPS_PORT` | `443` | Public HTTPS port. `.env.example` sets `8443`, because rootless Podman cannot bind ports below 1024 |
| `POSTGRES_HOST` / `POSTGRES_PORT` / `POSTGRES_DB` | `db` / `5432` / `lb42db` | |
| `POSTGRES_USER` / `POSTGRES_PASSWORD` | `lb42` / *required* | Provided as secrets |
| `SECRET_KEY` | random per process | See [Secrets](#secrets) |
| `FT_CLIENT_ID` / `FT_CLIENT_SECRET` | empty | While empty, `GET /api/auth/login` answers `503` |
| `FT_REDIRECT_URI` | `https://localhost:8443/api/auth/callback` | Must match the intra **byte for byte**. Set it whenever the public host or port changes |
| `FT_SCOPE` | `public` | Intra OAuth scope |
| `FT_AUTHORIZE_URL`, `FT_TOKEN_URL`, `FT_ME_URL` | intra endpoints | Only overridden in tests |
| `SESSION_MAX_AGE` | `604800` (7 days) | Lifetime of both the session cookie and the JWT |
| `SESSION_COOKIE_NAME` | `session` | |
| `OAUTH_STATE_MAX_AGE` | `600` (10 minutes) | Lifetime of the login-flow cookies |
| `COOKIE_SECURE` | `true` | Set to `false` only over plain HTTP (bare Uvicorn, tests) |
| `POST_LOGIN_REDIRECT` | `/` | Where the browser lands after the callback, relative to the site root |
| `REGISTER_BLOCKED_EMAIL_DOMAINS` | `student.42.fr` | Comma-separated email domains refused by `POST /api/auth/register` (their owners sign in with 42) |
| `PASSWORD_REAUTH_MAX_AGE` | `600` (10 minutes) | How recent the 42 login must be for a 42 account to set its first password |
| `CORS_ORIGINS` | empty | Comma-separated. Empty disables the CORS middleware |
| `WS_ALLOWED_ORIGINS` | empty | Comma-separated. Empty means `https://SERVER_NAME[:HTTPS_PORT]` |

- **`CORS_ORIGINS`** stays empty in Docker, because nginx serves the front and
  the API from the same origin. Set it only when the front runs standalone.
  Since the middleware allows credentials, it needs explicit origins:
  browsers reject `*` when cookies are involved.
- **`FT_REDIRECT_URI`** is derived from `SERVER_NAME` and `HTTPS_PORT` only
  when it is explicitly set to an empty string outside Compose. Compose always
  passes a value, so on another host set it in `.env`.

Quotas (`QUOTA_*`), rate limits (`RATE_*`) and WebSocket limits (`WS_*`) are
described in [Limits, quotas and rate limiting](#limits-quotas-and-rate-limiting)
and in the [real-time README](src/app/core/realtime/README.md#settings).

### Process settings

`entrypoint.sh` and Compose read these variables. `Settings` does not.

| Variable | Default | Notes |
|---|---|---|
| `UVICORN_WORKERS` | `1` | **Must stay 1**: see [Known limitations](#known-limitations) |
| `UVICORN_RELOAD` | unset (`true` in dev) | Run Uvicorn with `--reload` on `/app/src` |
| `SEED_DEMO_DATA` | `true` (in `.env.example`, and forced in dev) | Load the demo data at start. **Never in production**: the seed creates admin accounts |
| `WS_MAX_FRAME_BYTES` | `4096` | Passed to Uvicorn as `--ws-max-size`, and also enforced by the endpoint |
| `PGSSLMODE` | `disable` (set by Compose) | SSL mode for the asyncpg connection |

---

## API conventions

### Base paths

| Prefix | Content | Versioned |
|---|---|---|
| `/api/v1` | REST resources | Yes |
| `/api/auth` | 42 login, callback, logout; email/password register, login and password change | No. The callback URL is registered on the intra and must survive a `/api/v2` |
| `/api/ws` | WebSocket | No. A transport has no API version, and nginx upgrades only this location |

Everything stays under `/api/`, because that is the only prefix nginx sends to
the API. Any other path reaches the Next.js front.

### Identifiers

- **Users and listings** are addressed by `public_id`, a random UUID. The
  internal `BIGINT` key is never exposed. Responses also carry an `id` field
  that mirrors `public_id`, for the front's convenience.
- **Conversations, messages, friendships, reviews, reports, categories and
  locations** are addressed by their integer id. Apart from categories and
  locations, they are visible only to the people involved.
- **Reports and friend requests** return their integer id as a string
  (`"id": "12"`), matching the front's types. Paths take the number
  (`/reports/12/resolve`).
- **`cover_image_id`**, in listing responses, holds the **storage path** of
  the cover image, not an id. The name is kept for compatibility with the
  front.

### Requests and responses

- JSON everywhere, with `snake_case` fields. Successful responses return the
  resource or array directly, with no envelope.
- Actions that have no resource to return answer `{"message": "..."}`, for
  example `{"message": "Friend request sent"}`.
- Timestamps are timezone-aware ISO 8601, in UTC.
- Prices are integers in whole currency units. `currency` is a three-letter
  code, `EUR` by default.
- Every user object embedded in a response (seller, author, participant…) is
  a `PublicUser`: `public_id`, `id`, `display_name`, `avatar_path`, `bio`,
  `rating` (average, `0.0` without reviews), `rating_count` and `is_active`.

### Errors and status codes

Errors use FastAPI's format. A business error carries a readable message:

```json
{"detail": "Only the seller can delete this listing"}
```

A validation error (`422`) lists every invalid field, with its location:

```json
{"detail": [{"type": "less_than_equal", "loc": ["query", "limit"],
             "msg": "Input should be less than or equal to 100",
             "input": "500", "ctx": {"le": 100}}]}
```

| Status | Meaning in this API |
|---|---|
| `200` / `201` / `204` | Success. `201` on creation, `204` when there is no body |
| `303` / `307` | OAuth redirects (`/api/auth/*` only) |
| `400` | The request is well formed but not allowed as sent: acting on yourself (messaging your own listing; reviewing, blocking, reporting or sanctioning yourself; changing your own role), or a review that does not match its conversation |
| `401` | No valid session, or the account is suspended or deleted |
| `403` | Signed in but not allowed: wrong role, not the owner, a block between the two users, or a sanction above your rank |
| `404` | Not found. Also used instead of `403` where a `403` would reveal that something exists (conversations, friendships, report targets) |
| `409` | Conflicts with the current state: duplicate, already sold or closed, or a total quota reached |
| `422` | Validation failure. The error names the field |
| `429` | Rate limit (with a `Retry-After` header) or 24-hour quota |
| `503` | 42 login not configured |

### Pagination

**Offset pagination** takes `page` (1–10 000, default 1) and `limit` (1–100,
default 30). The paginated endpoints return an envelope:

```json
{ "data": [ ... ], "total": 42, "page": 1, "limit": 30, "total_pages": 2 }
```

It is used by `GET /listings`, `GET /users/{public_id}/listings`,
`GET /users/{public_id}/favorites` and the admin `GET /users`.
`GET /reports` is not paginated: it returns every report as a bare array.

**Cursor pagination** is used for message history. It takes `limit` (1–100,
default 30) and an optional `before_id`, and returns the newest messages older
than `before_id`, in chronological order. To load older history, pass the
smallest `id` received so far.

### Try it with curl

Public routes need nothing:

```bash
BASE=https://localhost:8443
curl -k "$BASE/api/v1/listings?limit=2&sort=price_asc"
curl -k "$BASE/api/v1/categories"
```

For authenticated routes, reuse a browser session:

1. sign in at `https://localhost:8443/api/auth/login`;
2. in the browser's developer tools (Application or Storage tab → Cookies),
   copy the value of the `session` cookie;
3. pass it to curl:

```bash
SESSION='eyJhbGciOiJIUzI1NiIs...'
curl -k -b "session=$SESSION" "$BASE/api/v1/auth/me"

curl -k -b "session=$SESSION" -H 'Content-Type: application/json' \
     -d '{"title": "Desk lamp", "body": "Works fine", "price": 15,
          "category_id": 1, "location_id": 1}' \
     "$BASE/api/v1/listings"
```

Take `category_id` and `location_id` from `GET /categories` and
`GET /locations`.

> [!TIP]
> Under `make dev`, Swagger UI (`/api/v1/docs`) runs on the same origin as the
> app. Once you are signed in in the same browser, its **Try it out** calls
> carry your session cookie.

---

## Authentication (42 OAuth2)

### Flow

The flow is a standard authorization-code grant. The browser never sees the
client secret. The intra access token is used once, server to server, and is
never stored.

```
1. GET /api/auth/login[?next=/some/page]
   -> random `state` (256 bits) stored in the HttpOnly `oauth_state` cookie
   -> sanitised `next` stored in the `oauth_next` cookie (both: Path=/api/auth/, 10 min)
   -> 307 to https://api.intra.42.fr/oauth/authorize (scope `public`)

2. the user approves on the intra
   -> the intra redirects the browser to /api/auth/callback?code=...&state=...

3. the API checks `state` against the cookie (constant-time), then, server to server:
   POST https://api.intra.42.fr/oauth/token   code + client secret -> access token
   GET  https://api.intra.42.fr/v2/me         Bearer token         -> profile

4. the API resolves the profile to a local user, signs a session JWT,
   sets the `session` cookie and answers 303 to `next` or POST_LOGIN_REDIRECT
```

`next` is accepted only if it is a path on this site. The API refuses
anything a browser could read as another host (`//host`, backslashes, control
characters), any `/api/…` path, and values longer than 512 characters. It
checks the value again when the cookie comes back.

**For the front:** send the user to `/api/auth/login?next=<current path>`
with a plain navigation (a link or `window.location`), never with `fetch`.
After the login, `GET /api/v1/users/me` tells whether a session exists
(`200`) or not (`204`).

### Email and password

Besides 42 OAuth2, an account can be created and used with an email and a
password. The three routes answer JSON (call them with `fetch`) and, on
success, set the same `session` cookie as the 42 callback:

- `POST /api/auth/register` (`email`, `password`, `display_name`) creates the
  account and opens a session: `201`. `409` if the email is taken (case
  ignored), `403` for a domain in `REGISTER_BLOCKED_EMAIL_DOMAINS`
  (`student.42.fr`: those students sign in with 42, and a local account on
  their address would lock them out with `email_taken`). `email_verified_at`
  stays `NULL`: no mail confirms the address yet.
- `POST /api/auth/login` (`email`, `password`) opens a session: `200`. An
  unknown email, a wrong password and a 42 account without a password all get
  the same `401`, after the same hashing work, so neither the answer nor its
  timing tells which emails have an account. `403` for a suspended or deleted
  account, only once the password is right.
- `POST /api/auth/password` (`new_password`, `current_password`) changes the
  password: `204`. `current_password` is required when the account has one
  (`400` if wrong). A 42 account without one can set a first password only
  from a session opened in the last `PASSWORD_REAUTH_MAX_AGE` seconds (10
  minutes), otherwise `403`: with no old password to prove, a fresh 42 login
  is the proof, so a computer left logged in is not enough.

Password checks (login and change) are limited per email, see
[Rate limiting](#rate-limiting-per-user), on top of the nginx `auth_per_ip`
zone. Passwords are 8 to 128 characters, kept as typed (not trimmed), and
hashed with **argon2id** (`argon2-cffi`, `core/passwords.py`), in a thread so
the event loop never waits on it. The plaintext is never stored or logged.
`GET /api/v1/auth/me` and `GET /api/v1/users/me` report `has_password`.

Changing a password does not end the other sessions: the JWT is stateless,
so they last until they expire (`SESSION_MAX_AGE`).

### Callback outcomes

The callback is a browser navigation, so it never answers with a JSON error.
Every outcome is a `303` redirect, and the two flow cookies are cleared either
way (single use):

- **success**: to `next` if one was given, otherwise to `POST_LOGIN_REDIRECT`,
  with the `session` cookie set;
- **failure**: to `POST_LOGIN_REDIRECT?auth_error=<code>`.

| `auth_error` | Cause | What to do |
|---|---|---|
| `denied` | The user declined on the intra, or the intra returned an `error` | Sign in again and approve |
| `invalid_state` | `state` is missing or does not match the cookie (expired, forged or replayed) | Start again from `/api/auth/login`, within 10 minutes |
| `invalid_code` | `code` is missing, or the intra refused it (expired or already used) | Start again. Also check `FT_REDIRECT_URI` and the client secret |
| `intra_unavailable` | Network error, error status or malformed response from the intra, other than a refused code | Retry later; the API logs show the intra's HTTP status |
| `invalid_profile` | The intra profile lacks `id`, `login` or `email` | Nothing on our side: the intra account is incomplete |
| `email_taken` | The email belongs to an existing account that has a password (see below) | An admin must resolve the conflict |
| `account_disabled` | The account is suspended or soft-deleted | A moderator or admin must reactivate it |
| `conflict` | A concurrent login collided and the account could not be recovered | Sign in again |

The codes are machine-readable and carry nothing sensitive. The logs hold the
details, including the intra's HTTP status, but never the response bodies,
which could echo the code or the token.

### Account resolution

A user's identity is their **numeric intra id**, stored in `oauth_accounts`
with `provider = '42'`. It is never the login, because a student can rename
their login. On each callback:

1. **Known 42 account.** The API refreshes `email` from the intra, which is
   its source of truth, and fills `avatar_path` only if it is empty.
   `display_name` is never overwritten: once set, it belongs to the user.
2. **No 42 account, but a user with the same email** (compared
   case-insensitively):
   - if that account has **no password**, it is linked (a new `oauth_accounts`
     row) and its avatar is filled if empty;
   - if it **has a password**, the login is refused with `email_taken`.
     Linking on an email match alone, without proof of ownership, would hand
     the 42 login someone else's password-protected account.
3. **Unknown user.** The API creates one: `display_name` is the 42 login,
   `avatar_path` the intra picture, `role` is `user`, and `email_verified_at`
   is set to now.

A suspended or soft-deleted account is refused (`account_disabled`) in every
case. If two callbacks for the same profile race, the loser rolls back and
reuses the account the winner created.

The initial schema already supports this, with no dedicated migration:
`users.password_hash` is nullable ("NULL for OAuth-only accounts"), and
`oauth_accounts(provider, provider_account_id)` is unique.

### Registering the application

1. Create an application on
   <https://profile.intra.42.fr/oauth/applications>.
2. Register the redirect URI for your setup. The intra matches it **byte for
   byte**:

   | Setup | Redirect URI |
   |---|---|
   | `make dev` / `make up` (through nginx) | `https://localhost:8443/api/auth/callback` |
   | Bare `uv run uvicorn app.main:app` | `http://localhost:8000/api/auth/callback` |

   That means the same scheme, `localhost` and never `127.0.0.1`, no trailing
   slash, and the port the **browser** sees (the host side of the Docker
   mapping, `HTTPS_PORT`). No tunnel is needed: the browser calls localhost,
   and the 42 servers never do.
3. Paste the application's UID and secret into `secrets/FT_CLIENT_ID` and
   `secrets/FT_CLIENT_SECRET`, or let `make dev` prompt for them.
4. Restart the stack (`make down`, then `make dev` or `make up`) so that the
   `api` container reads them.

### Session

- **Token**: an HS256 JWT signed with `SECRET_KEY`, with claims `sub` (the
  user's `public_id`), `iat` and `exp`. The role is **not** in the token.
- **Cookie**: `session`, `HttpOnly`, `SameSite=Lax`, `Secure` (unless
  `COOKIE_SECURE=false`), `Path=/`, with a lifetime of `SESSION_MAX_AGE`
  (7 days).
- **Per request**: the API loads the user from the database on every
  authenticated request, and refuses a deactivated (`is_active = false`) or
  soft-deleted (`deleted_at` set) account. A role change or a suspension
  therefore applies to REST calls immediately, without a new login.
- **Logout**: `POST /api/auth/logout` clears the cookie and closes the user's
  WebSocket connections on every device. Devices that are still logged in
  reconnect.
- **Revocation**: sessions are stateless and there is no session table. A
  token copied before logout stays valid until it expires. Revoking access
  early means suspending or deleting the account, or rotating `SECRET_KEY`,
  which logs out everyone.

---

## Authorization

### Roles

`users.role` is a foreign key into the `roles` lookup table, which the initial
migration seeds with `user`, `moderator` and `admin`. New accounts are `user`.
Only an admin can change a role, through `PATCH /api/v1/users/{public_id}/role`.
Permissions are granted in code, so a role added to the table later has the
rights of a plain user until the code knows about it.

| Role | Can do |
|---|---|
| `user` | Everything a signed-in user can do: listings, messages, friends, reviews, reports |
| `moderator` | Plus the moderation queue (`/reports` list, resolve, reject, reopen) |
| `admin` | Plus user management (`/users` admin routes) and the analytics dashboard |

To give yourself a role on a **development** database, see
[Troubleshooting](#troubleshooting).

### Dependencies

Access is declared per route with FastAPI dependencies from
[`core/security.py`](src/app/core/security.py):

| Dependency | Anonymous | Wrong role | Returns |
|---|---|---|---|
| `get_current_user` | `401` | — | The active `User` |
| `get_current_user_optional` | `None` | — | `User` or `None`, for public routes that personalise their response |
| `get_current_moderator` | `401` | `403` | The `User`, if `moderator` or `admin` |
| `require_admin` | `401` | `403` | The `User`, if `admin` |
| `require_admin_stream` | `401` | `403` | Same as `require_admin`, but opens and closes its own database session. For the SSE stream, which would otherwise hold a pool connection for its whole lifetime |

### Sanction hierarchy

Moderation actions against an account (suspend, remove) follow
`can_sanction`. The actor's rank must be **strictly higher** than the
target's (`user` 0, `moderator` 1, `admin` 2), and nobody can sanction
themselves:

| Actor | Can sanction |
|---|---|
| `moderator` | Users only |
| `admin` | Users and moderators |
| anyone | Never an admin, never themselves |

The admin routes follow their own rules. An admin can change any other
account's role and delete any other account, but never their own. See
[Admin user management](#admin-user-management).

### Protecting a route

```python
from fastapi import Depends
from app.core.security import get_current_user
from app.models import User

@router.post("/listings", status_code=201)
async def create_listing(payload: ListingCreate, user: User = Depends(get_current_user)):
    ...  # user.id is the seller
```

For a role, use `Depends(get_current_moderator)` or `Depends(require_admin)`.
For a public route that adapts to the viewer, use
`Depends(get_current_user_optional)`.

---

## Endpoint reference

Every path below `/api/v1` is relative to that prefix. Request and response
schemas are in the OpenAPI schema (`/api/openapi.json`).

**Access** reads as follows:

- **Public**: no session needed.
- **Public\***: public, but personalised when a session is present.
- **User**: any signed-in user.
- **Moderator** / **Admin**: that role or higher.
- **Owner**, **Seller**, **Participant**, **Friend**, **Addressee**,
  **Requester**: a signed-in user with that relationship to the resource.

**OK** is the status of a successful response.

### Authentication and service

| Method | Path | Access | OK | Description |
|---|---|---|---|---|
| `GET` | `/api/auth/login` | Public | `307` | Starts the 42 login. Optional `next` (a path on this site). `503` if not configured |
| `POST` | `/api/auth/login` | Public | `200` | Email/password login, opens the session |
| `GET` | `/api/auth/callback` | Public | `303` | OAuth redirect target. Always a redirect to the app, with `?auth_error=` on failure |
| `POST` | `/api/auth/register` | Public | `201` | Creates an email/password account and opens the session |
| `POST` | `/api/auth/password` | User | `204` | Sets or changes the password |
| `POST` | `/api/auth/logout` | Public | `204` | Clears the session cookie and closes the user's sockets |
| `GET` | `/auth/me` | User | `200` | Current user: `public_id`, `display_name`, `email`, `role`, `avatar_path`, `bio`, `has_password` |
| `GET` | `/health` | Public | `200` | Liveness probe, returns `{"status": "ok"}`. Does not query the database |
| `GET` | `/metrics` | Internal | `200` | Prometheus metrics. Served at the app root and not routed by nginx |

### Catalog

| Method | Path | Access | OK | Description |
|---|---|---|---|---|
| `GET` | `/categories` | Public | `200` | All categories with their attribute definitions, by depth then name |
| `GET` | `/locations` | Public | `200` | All campuses, by name |

### Listings and favorites

| Method | Path | Access | OK | Description |
|---|---|---|---|---|
| `GET` | `/listings` | Public\* | `200` | Active listings, paginated, without those of suspended or removed sellers. Filters: `q`, `categorie`, `location`, `prix_min`, `prix_max`. Sort: `sort`. Signed in: your own listings are excluded and `is_favorited` is filled |
| `GET` | `/listings/{public_id}` | Public\* | `200` | Any listing that is not deleted, with its images |
| `POST` | `/listings` | User | `201` | Create a listing, published at once as `active` |
| `DELETE` | `/listings/{public_id}` | Owner | `204` | Soft delete. `409` if already sold |
| `POST` | `/listings/{public_id}/mark-sold` | Owner | `204` | Sold outside the app: no buyer recorded, so no review possible |
| `POST` | `/listings/{public_id}/favorite` | User | `200` | Add to favorites (idempotent). Returns `is_favorited` and `favorites_count` |
| `DELETE` | `/listings/{public_id}/favorite` | User | `200` | Remove from favorites (idempotent) |

### Users, profiles and blocks

| Method | Path | Access | OK | Description |
|---|---|---|---|---|
| `GET` | `/users/me` | Public | `200` | Own profile, with `email`, `location_id` and counts. **`204`** without a session |
| `PATCH` | `/users/me` | User | `200` | Partial update of `display_name`, `bio`, `avatar_path`, `location_id` |
| `GET` | `/users/me/stats` | User | `200` | [Personal statistics](#personal-statistics) |
| `GET` | `/users/me/blocks` | User | `200` | Users I blocked, most recent first |
| `GET` | `/users/{public_id}` | Public\* | `200` | Public profile with role. `has_blocked_me` tells the caller whether this user blocked them |
| `GET` | `/users/{public_id}/reviews` | Public | `200` | Reviews received, newest first |
| `GET` | `/users/{public_id}/listings` | Public\* | `200` | The user's active and sold listings, paginated |
| `GET` | `/users/{public_id}/favorites` | Public\* | `200` | The user's favorites (deleted listings excluded), paginated. `is_favorited` refers to the viewer |
| `GET` | `/users/{public_id}/friends` | User | `200` | The user's accepted friends |
| `POST` | `/users/{public_id}/block` | User | `200` | Block a user. See [Blocking](#blocking) |
| `DELETE` | `/users/{public_id}/block` | User | `200` | Unblock a user (idempotent) |

### Friends and direct messages

| Method | Path | Access | OK | Description |
|---|---|---|---|---|
| `POST` | `/friends` | User | `201` | Send a friend request. Body: `{"user_id": "<uuid>"}` |
| `GET` | `/friends/pending` | User | `200` | Requests received and not yet answered |
| `POST` | `/friends/{request_id}/accept` | Addressee | `200` | Accept a pending request |
| `POST` | `/friends/{request_id}/decline` | Addressee | `200` | Decline, which deletes the request |
| `DELETE` | `/friends/requests/{public_id}` | Requester | `200` | Cancel my pending request to that user |
| `DELETE` | `/friends/{public_id}` | Friend | `200` | End the friendship. **Deletes the direct-message history** |
| `GET` | `/friends/messages` | User | `200` | Direct-message inbox: one entry per friend, latest activity first |
| `GET` | `/friends/{public_id}/messages` | Friend | `200` | Message history, cursor-paginated |
| `POST` | `/friends/{public_id}/messages` | Friend | `201` | Send a message. Body: `{"body": "..."}`. Pushed as `friend_message.created` |

### Listing conversations

| Method | Path | Access | OK | Description |
|---|---|---|---|---|
| `POST` | `/conversations/listing` | User | `201` | Get or create my conversation with the seller. Body: `{"listing_id": "<uuid>"}`. `201` in both cases |
| `GET` | `/conversations` | User | `200` | All my conversations, as buyer or seller, including closed ones. Newest first |
| `DELETE` | `/conversations/{id}` | Participant | `204` | Close the conversation for both sides. Messages are kept |
| `POST` | `/conversations/{id}/mark-sold` | Seller | `200` | Mark the listing sold to this conversation's buyer |
| `GET` | `/conversations/{id}/messages` | Participant | `200` | Message history, cursor-paginated |
| `POST` | `/conversations/{id}/messages` | Participant | `201` | Send a message. Body: `{"body": "..."}`. Pushed as `message.created` |

Conversation summaries carry `type: "listing"`, and direct-message summaries
`type: "friend"`, so the front can merge both into one inbox.

### Reviews

| Method | Path | Access | OK | Description |
|---|---|---|---|---|
| `POST` | `/reviews` | Participant | `201` | Review the other side of a completed sale. Body: `conversation_id`, `subject_id`, `rating` (1–5), optional `body` |
| `DELETE` | `/reviews/{id}` | Author | `204` | Soft-delete my own review and take it out of the subject's rating |

### Uploads

| Method | Path | Access | OK | Description |
|---|---|---|---|---|
| `POST` | `/uploads/images` | User | `201` | Upload one image (multipart field `file`). Returns `{"path": "/media/..."}`, to put in `image_urls` or `avatar_path`. See [Image uploads](#image-uploads) |

### Moderation

| Method | Path | Access | OK | Description |
|---|---|---|---|---|
| `POST` | `/reports` | User | `201` | Report a listing, message, user or review. Body: `target_type`, `target_id`, `reason` |
| `GET` | `/reports` | Moderator | `200` | Every report, newest first, as a bare array (not paginated). Filters: `status`, `target_type` |
| `POST` | `/reports/{id}/resolve` | Moderator | `200` | Act on a report: `delete_target` or `block_user` |
| `POST` | `/reports/{id}/reject` | Moderator | `200` | Dismiss a report without action |
| `POST` | `/reports/{id}/reopen` | Moderator | `200` | Reopen a closed report, optionally undoing its action |

### Administration

| Method | Path | Access | OK | Description |
|---|---|---|---|---|
| `GET` | `/users` | Admin | `200` | Every account with its role, paginated. Filters: `q` (display name), `role` |
| `PATCH` | `/users/{public_id}/role` | Admin | `200` | Change an account's role. Body: `{"role": "moderator"}` |
| `DELETE` | `/users/{public_id}` | Admin | `204` | **Permanently** delete an account and everything it owns |

### Analytics

All of these are **Admin** only and answer `200`. See
[Admin analytics](#admin-analytics) for the definitions.

| Method | Path | Description |
|---|---|---|
| `GET` | `/analytics` | The whole dashboard in one response. Accepts `startDate` and `endDate` |
| `GET` | `/analytics/online-students` | Users active in the last 5 minutes, by campus, with today's peak |
| `GET` | `/analytics/listings-today` | Listings posted today, change from yesterday, by category |
| `GET` | `/analytics/pending-reports` | Open reports by target type, urgent count, oldest date |
| `GET` | `/analytics/sold-percentage` | Share of the stock sold, average time to sell |
| `GET` | `/analytics/category-distribution` | Posted listings per category |
| `GET` | `/analytics/listings-between-dates` | Daily counts between `startDate` and `endDate` |
| `GET` | `/analytics/total-value` | Value of the stock, active and sold, by category |
| `GET` | `/analytics/average-price` | Mean, median, minimum and maximum price, and mean by category |
| `GET` | `/analytics/messages-count` | Listing-chat activity |
| `GET` | `/analytics/top-liked` | The five most favorited active listings |
| `GET` | `/analytics/stream` | Server-Sent Events stream of dashboard invalidations. Not in the OpenAPI schema |

### Real-time endpoint

| Protocol | Path | Access | Description |
|---|---|---|---|
| WebSocket | `/api/ws` | User | Real-time events and typing indicators. See [Real-time](#real-time) |

---

## Business rules

This section documents what the code enforces beyond what the endpoint
tables show.

### Listings

- **Status** is one of `draft`, `active`, `sold`, `expired`, `archived` or
  `deleted`, enforced by a `CHECK` constraint. The API currently uses three of
  them: listings are created `active`, and become `sold` or `deleted`.
- **Creation** takes `title`, `body` (may be empty), `price`, `category_id`
  and `location_id`, plus optional `currency` (`EUR` by default), `condition`
  (`new`, `like_new`, `good`, `fair` or `for_parts`), `attributes` (a JSON
  object) and `image_urls` (up to 10).
  - The category and the location must exist (`404` otherwise).
  - The first entry of `image_urls` becomes the cover image, and the order is
    kept as `position`.
- **Browsing** (`GET /listings`) returns `active` listings only:
  - `q` matches the title or the body, case-insensitively;
  - `categorie` is an exact category id, so subcategories are not included;
  - `location` is an exact campus id;
  - `prix_min` and `prix_max` bound the price, inclusive;
  - `sort` is one of `recent` (the default), `oldest`, `price_asc`,
    `price_desc` or `likes_desc` (most favorited first).
- **A suspended or removed seller's listings are left out of `GET /listings`**,
  and are back if the account is reactivated. Only this list is filtered:
  such a listing still opens by its address, and still shows on profiles and
  in favorites.
- **Deletion** is soft: `status = deleted` and `deleted_at` are set, so the
  conversations and messages about the listing are kept. A sold listing
  cannot be deleted (`409`), so that the buyer can still leave a review.
- **Selling** has two routes. Both require the listing to be `active` (`409`
  otherwise), so a listing can be sold only once:
  - through a conversation, `POST /conversations/{id}/mark-sold` records that
    conversation's buyer in `listings.buyer_id`, which is what allows both
    sides to review each other;
  - `POST /listings/{public_id}/mark-sold` is for sales outside the app,
    records no buyer, and so allows no review.

### Listing conversations

- There is one conversation per buyer and listing, enforced by a unique
  constraint. Asking again returns the existing one.
- You cannot open a conversation on your own listing (`400`), or with a
  seller when either of you has blocked the other (`403`).
- Closing a conversation (`DELETE`) affects both participants: sending then
  answers `409`. No endpoint reopens it; only [unblocking](#blocking) reopens
  conversations.
- Every message is pushed to both participants' `user:<public_id>` topics,
  including the sender, so that their other tabs stay in sync.

### Reviews

A review requires all of the following:

- the author took part in the conversation (`403` otherwise);
- the subject is the **other** participant (`400`);
- the listing was **sold through that conversation**: `status = sold` and
  `buyer_id` is the conversation's buyer (`400`);
- there is at most one review per author per conversation (`409`).

Buyer and seller can therefore review each other once per sale.

`users.rating` stores the **sum** of the ratings received, and
`users.rating_count` their number. The API exposes the average
(`rating / rating_count`) in every public user object. The counters are
updated when a review is created, removed or restored by moderation, and when
its author is deleted.

### Friends and direct messages

- A request is `pending` until the addressee accepts it (`accepted`). There
  can be only one row between two users, in either direction, whatever its
  status (`409`).
- Declining or cancelling deletes the request. Ending a friendship deletes
  the friendship **and its direct messages** (`ON DELETE CASCADE`).
- Reading or sending direct messages requires an accepted friendship. When
  there is none, the API answers `404`, so as not to reveal whether a pending
  request exists.
- `GET /friends/pending` hides requests from deleted users and from users
  you blocked.

### Blocking

Blocking a user (`POST /users/{public_id}/block`) does three things in one
transaction:

1. records the block. It is idempotent, and safe against double submits
   (`ON CONFLICT DO NOTHING`);
2. deletes any friendship or pending request between the two users, in
   either direction, together with their direct messages;
3. closes every open conversation between them, whichever side is the buyer.

While a block exists **in either direction**, the two users cannot:

- send each other listing messages;
- open a conversation on each other's listings;
- send each other friend requests (all `403`);
- see each other's typing indicators, which are dropped.

Unblocking deletes the block and reopens **every** closed conversation
between the two users, including any closed by hand before the block. It
does not restore the friendship, which needs a new request.

Blocks do **not** hide [presence](#websocket): both users still see whether
the other is online.

### Moderation

**Reporting.**

- `target_type` is `listing`, `message`, `user` or `review`.
- `target_id` is the `public_id` (UUID) for listings and users, and the
  integer id for messages and reviews. A JSON number is accepted for those.
  Messages here are listing-chat messages: direct messages between friends
  cannot be reported.
- The target must exist and not already be removed (`404`).
- You cannot report yourself (`400`).
- A reporter can have at most one open report per target (`409`).

**Statuses.** A report is `open` until a moderator acts on it:

```
            resolve                     reject
 resolved ◀──────────── open ────────────▶ closed
     │                   ▲                    │
     └───── reopen ──────┴────── reopen ──────┘
```

An action on a report that is already `resolved` or `closed` answers `409`.
`in_progress` exists in the schema, but no route sets it yet.

**Resolve actions.**

| Action | Body | Effect |
|---|---|---|
| `delete_target` | `{"action": "delete_target"}` | Soft-removes the reported target: a listing becomes `deleted`; a message or review gets `deleted_at`, and a review's rating is taken out of its subject's counters; a user gets `deleted_at` and `is_active = false`, subject to the [sanction hierarchy](#sanction-hierarchy). Add `target_type` and `target_id` together to act on another target than the reported one |
| `block_user` | `{"action": "block_user", "user_id": "<uuid>"}` | **Suspends** that account (`is_active = false`), subject to the sanction hierarchy, never yourself |

After either action:

- every other open report on the same target is resolved too;
- a suspended or removed user is refused by every REST route from then on;
- that user's WebSocket connections are closed.

Report rows are locked (`SELECT … FOR UPDATE`), so two moderators cannot act
on the same report at once.

**Reopen.** The optional body undoes the action:

- `{"action": "restore_target"}` reverses a removal. A listing comes back as
  **`active`**, whatever its status was before, because the previous status
  is not recorded. A message or review is restored, together with its rating.
  A user is undeleted and reactivated.
- `{"action": "unblock_user", "user_id": "<uuid>"}` reactivates that account
  and clears any soft delete. This path does not apply the sanction
  hierarchy.

Without a body, only the status changes. Reports closed together with the
reopened one stay closed.

### Admin user management

In [`api/v1/admin_users.py`](src/app/api/v1/admin_users.py). All routes are
admin only: `401` when anonymous, `403` for a user or a moderator.

- **`GET /users`** lists every account, newest first, paginated (at most 100
  per page).
  - `q` searches the display name, case-insensitively, with `%` and `_`
    treated literally.
  - `role` filters on an exact role.
  - Suspended and soft-deleted accounts are included on purpose.
  - Rows carry no email.
- **`PATCH /users/{public_id}/role`** takes `{"role": ...}` and accepts any
  role present in the `roles` table (`422` otherwise).
  - The role is read from the database on every request, so the change
    applies at once, without a new login.
  - Nobody can change their own role (`400`), which guarantees that at least
    one admin always remains.
  - A soft-deleted account answers `404`.
- **`DELETE /users/{public_id}`** is a **real, irreversible delete** (`204`).
  The moderation action `delete_target` on a user, by contrast, is a
  reversible soft delete. Nobody can delete themselves (`400`).
  - **Cascade.** `ON DELETE CASCADE` deletes:
    - their listings, with the conversations, messages and favorites on them;
    - their conversations as a buyer;
    - the reviews they wrote **and** received;
    - friendships and direct messages, blocks, favorites, saved searches;
    - the reports they filed, and their OAuth accounts.

    The other participants in those conversations therefore lose the shared
    history. Listings they bought from others stay, with `buyer_id` set to
    `NULL`.
  - **Before the cascade**, the API does what the cascade cannot: the
    ratings of the reviews they wrote are taken out of the counters of the
    people they reviewed.
  - **Reports about them** keep a `target_id` that points at nothing. There
    is no foreign key, and the moderation code handles a missing target by
    returning `target: null`.
  - **Afterwards**, their WebSocket connections are closed, and their session
    answers `401`.

### Personal statistics

`GET /users/me/stats` returns the caller's own figures, computed in SQL.
Prices are whole euros, taken from the listing's current price (there is no
price history), and are all assumed to be EUR.

- **selling**: my listings that are `active` or `sold` and not deleted.
  - `count`, `total_value` (sum of prices) and `average_price` for each of
    the two statuses;
  - a breakdown by category, with the `active` and `sold` counts.
  - Drafts, expired, archived and deleted listings are not counted.
- **buying**: listings whose `buyer_id` is me (set when the seller marks the
  listing sold through our conversation) and that are `sold` and not deleted.
  - `count`, `total_spent`, `average_price`, and a breakdown by category.
  - A purchase whose listing was deleted afterwards is no longer counted.

Averages are rounded to two decimals, and are `0` when there is nothing to
average. Categories are sorted biggest first. Listings without a category
appear with `category_id: null`. There is no time series: the figures describe
the current state only.

### Admin analytics

These definitions apply to every `/analytics` endpoint:

- **Time zone.** "Today" and daily buckets use **Europe/Paris**.
- **Posted listings** are listings that are not deleted and not drafts:
  `active`, `sold`, `expired` or `archived`.
- **Stock** means `active` or `sold`, not deleted. The definition is in
  [`core/listing_filters.py`](src/app/core/listing_filters.py) and shared
  with the personal statistics, so the two cannot drift apart.

| Endpoint | Definition |
|---|---|
| `online-students` | Users who made an authenticated request (REST call, WebSocket handshake or SSE connection) in the last 5 minutes, grouped by their campus (`users.location_id`). `peak_today` is the highest total observed today |
| `listings-today` | Posted listings created today, % change from yesterday (`100` when yesterday had none and today has some), by category |
| `pending-reports` | Reports with status `open`, by target type. `urgent_count` counts those whose reason contains `arnaque`, `suspect` or `harcèlement` (French keywords matching the language of user reports), case-insensitively |
| `sold-percentage` | `sold / (sold + active)` over the stock. `average_time_to_sell_days` runs from `created_at` to `updated_at`, as there is no `sold_at` column |
| `category-distribution` | Posted listings per category, with percentages |
| `listings-between-dates` | Posted listings per day, with days that have no listings included as `0`. `startDate` and `endDate` are `YYYY-MM-DD`, default to the last 30 days, and are swapped if reversed. A range above 366 days answers `422` |
| `total-value` | Sum of the stock's prices: total, active, sold, and by category |
| `average-price` | Over posted listings with a price above 0: mean, median, minimum, maximum, and mean by category |
| `messages-count` | Listing-chat messages that are not deleted: total, today, number of conversations, conversations active today, average per conversation. Direct messages between friends are not counted |
| `top-liked` | The top 5 `active` listings by favorites, then views, then recency |

`online-students` and its peak live in process memory. They reset on restart,
and the peak records only values observed when the endpoint is called.

### Deletion policy

| Entity | Removed by | Kind | Reversible |
|---|---|---|---|
| Listing | Seller (`DELETE /listings/…`) | Soft (`status = deleted`, `deleted_at`) | No endpoint |
| Listing, message, review | Moderation `delete_target` | Soft (`deleted_at`) | Yes: reopen with `restore_target` |
| User | Moderation `delete_target` | Soft (`deleted_at`, `is_active = false`) | Yes: reopen with `restore_target` |
| User | Moderation `block_user` (suspension) | `is_active = false` | Yes: reopen with `unblock_user` |
| User | Admin `DELETE /users/…` | **Hard**, with cascade | **No** |
| Friend request, friendship | Decline, cancel, unfriend, block | Hard (direct messages cascade) | No |
| Favorite, block | Owner | Hard | Re-create |
| Conversation | Never deleted | `DELETE` closes it | Unblock reopens it |

A message removed by moderation is still returned in the conversation
history, body included, with `deleted_at` set. Clients are expected to hide
it.

---

## Real-time

The backend pushes to browsers over two channels:

| Channel | Path | For | Carries |
|---|---|---|---|
| WebSocket | `/api/ws` | Every signed-in user | New messages, typing indicators, presence |
| Server-Sent Events | `/api/v1/analytics/stream` | Admin dashboard | "Refresh now" signals, no data |

### WebSocket

A single authenticated WebSocket per browser tab carries every push event.
This section covers how the application uses it. The generic core (wire
protocol, session resume, delivery guarantees, close codes, limits) is
documented in [`src/app/core/realtime/README.md`](src/app/core/realtime/README.md),
and the browser client in
[`front/src/lib/realtime/README.md`](../front/src/lib/realtime/README.md).

**Handshake.** `/api/ws` accepts a connection only when both of these hold:

1. the `Origin` header is in `WS_ALLOWED_ORIGINS`, by default the origin nginx
   serves. A missing `Origin` is refused. This prevents cross-site WebSocket
   hijacking, since the browser attaches the session cookie to any page's
   handshake;
2. the session cookie decodes, through the same code as the REST routes, to
   an active user.

Otherwise the socket is closed before being accepted, which the client sees
as an HTTP `403`.

**Lifetime.** A socket never outlives the JWT that opened it. It is also
closed when the user logs out, is suspended or removed by moderation, or is
deleted by an admin (close code `4001`).

**Topics and events** (see [`realtime_topics.py`](src/app/realtime_topics.py)):

| Topic | Who may subscribe | Events |
|---|---|---|
| `user:<public_id>` | That user only | `message.created`, `friend_message.created`, `typing`, `friend_typing` |
| `presence` | Any signed-in user | `presence.snapshot` on subscribe (`{"online": [<public_id>…]}`), `presence.changed` (`{"user_id", "status": "online"\|"offline"}`) |

- The `message.created` and `friend_message.created` payloads are the same
  objects the matching `POST …/messages` route returns. They are published
  only after the database commit.
- Presence counts open sockets: a user is online from their first socket to
  their last. It does not filter blocked users.

**Client messages:**

| Type | Payload | Relayed when |
|---|---|---|
| `typing` | `{"conversation_id": int, "is_typing": bool}` | The sender takes part in the conversation, it is open, and neither side blocked the other |
| `friend_typing` | `{"friend_id": int, "is_typing": bool}` | The friendship is accepted, the sender is in it, and neither side blocked the other |

A relay that fails its check is dropped silently. The recipient receives the
payload plus `user_id`, the sender's `public_id`.

### Server-Sent Events (admin dashboard)

`GET /api/v1/analytics/stream` (admin) tells open dashboards when to refresh.
It carries **no business data**: clients refetch the REST endpoints. The
sequence diagram is in [`../schema_design.md`](../schema_design.md#sse-architecture).

```
retry: 3000

event: connected
data: {}

event: analytics_update
data: {"reason": "listing.created", "at": "2026-09-30T12:00:00+00:00"}

: ping
```

- **Reasons**: `listing.created`, `listing.deleted`, `listing.sold` (sold
  through a conversation), `favorite.added`, `favorite.removed`,
  `report.created`, `report.resolved`, `report.rejected`, `report.reopened`.
  They are published after the commit.
- **Keepalive**: after 20 seconds without an event, a `: ping` comment keeps
  the connection open, since nginx's `proxy_read_timeout` is 60 seconds.
- **Coalescing**: each subscriber queue holds one entry, so a burst of changes
  collapses into the latest invalidation.
- **Proxying**: `X-Accel-Buffering: no` disables nginx buffering for the
  stream. The route is excluded from the Prometheus metrics.
- **Database**: the authentication dependency uses and closes its own
  database session before the stream starts, so a long-lived dashboard holds
  no pool connection.

### Two notions of "online"

| Where | Meaning |
|---|---|
| `presence` topic (WebSocket) | The user has at least one WebSocket open right now. Drives the online indicators in the front |
| `/analytics/online-students` | The user made an authenticated request in the last 5 minutes. Drives the admin dashboard |

---

## Limits, quotas and rate limiting

A signed-in user must not be able to write a huge row, fill the database, or
flood the API. The protections stack from the cheapest check to the most
specific:

| Layer | What it caps | Answers | Where |
|---|---|---|---|
| nginx | Request body on `/api/`: 64 KB, 6 MB for image uploads (the front keeps 10 MB). Requests per IP | `413`, `429` | [`../nginx/nginx.conf`](../nginx/nginx.conf), `nginx.dev.conf` |
| Field limits | Length of every text field, price, image and attribute counts, ids, page number, search text | `422` | [`schemas/limits.py`](src/app/schemas/limits.py) |
| Quotas | Rows one user can own, or create per 24 hours | `409`, `429` | [`core/quotas.py`](src/app/core/quotas.py) |
| Rate limits | Requests per user per minute or hour | `429` | [`core/ratelimit.py`](src/app/core/ratelimit.py) |
| WebSocket | Frame size, frames per 10 s, sessions per user, topics per session | Close code or `error` frame | `ws_*` in [`core/config.py`](src/app/core/config.py) |

> [!TIP]
> **Tuning for a demo.** Quotas and rate limits are settings: add the
> `QUOTA_*` or `RATE_*` variable to the `api` `environment:` block in
> [`../docker-compose.yml`](../docker-compose.yml), then restart. `RATE_*=0`
> turns a rate limit off. For quotas, use a large number instead: `0` refuses
> everything.

### Field limits

A request over a limit answers **`422`**, naming the field.

| Field | Limit |
|---|---|
| Message body (listing chat, direct message) | 1–2000 characters |
| Review body | 0–1000 characters |
| Report reason | 1–1000 characters |
| Bio | 0–500 characters |
| Display name | 1–50 characters |
| Avatar path | 0–500 characters |
| Listing title | 1–120 characters |
| Listing body | 0–5000 characters |
| Listing price | 0 to 10 000 000 |
| Listing currency | 3 capital letters |
| Images per listing | 10, each URL up to 500 characters |
| Listing attributes | 20 keys, 2 KB of JSON |
| Report target id | 64 characters |
| Search text (`q`) | 100 characters |
| Page number | 1 to 10 000 |
| Any database id in a path, body or query | 1 to 2⁶³ − 1 |

- Text is stripped of surrounding whitespace before it is measured. A message
  made of spaces is therefore empty (`422`), and text is stored without its
  surrounding whitespace.
- Ids are capped at `2**63 - 1` (`BIGINT`): above that, the database would
  raise an error, which would be a `500` instead of a `404`.
- The values are constants, not settings. The front's inputs carry the same
  `maxLength`, so a change is a change of contract: update both sides.

### Quotas

Field limits bound a single request. Quotas bound how many rows a user can
create. The two kinds answer differently, so the client can tell them apart:

- a quota on a **total** answers **`409`**: the user has to delete something
  first;
- a quota on a **24-hour window** answers **`429`**: it frees up by itself.

| Setting | Default | Status | Counts |
|---|---|---|---|
| `quota_active_listings` | 50 | `409` | My listings that are active or draft, not deleted |
| `quota_listings_per_day` | 20 | `429` | Listings created in 24 h, **deleted ones included** (otherwise create/delete would be a loop) |
| `quota_conversations_per_day` | 30 | `429` | New conversations opened as a buyer in 24 h. Reopening an existing one does not count |
| `quota_messages_per_conversation` | 5000 | `409` | Messages in one listing chat or one friend conversation |
| `quota_reports_per_day` | 10 | `429` | Reports sent in 24 h |
| `quota_pending_friend_requests` | 50 | `409` | Requests I sent that nobody has answered |
| `quota_friends` | 500 | `409` | Accepted friendships, in either direction. Checked for the sender of a request, and for both users on accept |
| `quota_favorites` | 500 | `409` | Favorites. Adding one already there is not refused |
| `quota_blocks` | 500 | `409` | Users I blocked. Blocking one already blocked is not refused |

`0` refuses every creation. To relax a quota, use a large number.

**How it stays correct under load.** `enforce(...)` counts and inserts in the
same transaction. It first locks the user's row with
`SELECT … FOR NO KEY UPDATE`, so that parallel requests from one user queue up
instead of all slipping under the cap. `FOR UPDATE` is avoided on purpose:
foreign-key checks take `FOR KEY SHARE` on the user rows, so two users acting
on each other at the same moment would deadlock. `lock=False` skips the lock
for coarse caps where it would only slow every request down (messages per
conversation).

### Rate limiting (per user)

Quotas cap what is stored. Rate limits cap how fast it is requested.
`core/ratelimit.py` limits the `/api/v1` routes per signed-in user, with a
sliding window, and answers **`429`** with a `Retry-After` header in seconds.

| Setting | Default | Counts | Routes |
|---|---|---|---|
| `rate_reads_per_minute` | 300 | Every `GET`, all routes together | All of `/api/v1` |
| `rate_writes_per_minute` | 60 | Every `POST`, `PATCH` and `DELETE`, all routes together | All of `/api/v1` |
| `rate_messages_per_minute` | 30 | Listing-chat and direct messages, together | `POST …/messages` |
| `rate_listings_per_hour` | 10 | Listings created | `POST /listings` |
| `rate_reports_per_hour` | 10 | Reports sent | `POST /reports` |
| `rate_friend_requests_per_hour` | 20 | Friend requests sent | `POST /friends` |
| `rate_password_attempts_per_hour` | 10 | Password checks **per email**, whoever asks, signed in or not | `POST /api/auth/login`, `POST /api/auth/password` |

- A request counts in its global bucket (reads or writes) **and** in its own
  bucket when it has one: sending a message uses one of the 60 writes and one
  of the 30 messages. Refused requests do not extend the wait.
- **`0` turns a bucket off**, like `ws_rate_limit_per_10s`. This is the
  opposite of the quotas, where `0` refuses everything.
- The user is identified from the session cookie: the JWT is verified, with
  no database lookup, so a refused request costs almost nothing. A missing or
  invalid cookie is not limited here, and the route itself answers `401`.
  Anonymous traffic is limited per IP by nginx.
- The counters live in process memory: they assume one worker and reset on
  restart.

### Rate limiting (per IP, nginx)

Below the per-user limits, nginx caps requests per IP address (`limit_req`).
That is also what limits traffic without a session. Over the limit, nginx
answers **`429`** with `Retry-After: 1` and the body
`{"detail": "Too many requests, slow down"}`. The API's own `429` responses
pass through untouched.

| Zone | Location | Rate | Burst |
|---|---|---|---|
| `api_per_ip` | `/api/` | 100 requests/s | 200 |
| `auth_per_ip` | `/api/auth/` (42 login, callback, logout, email/password routes) | 30 requests/min | 20 |
| `ws_per_ip` | `/api/ws` (handshakes) | 10 requests/s | 20 |
| `upload_per_ip` | `/api/v1/uploads/` (image uploads) | 60 requests/min | 20 |
| `web_per_ip` | `/` (the front's pages, not its static files) | 100 requests/s | 200 |

An IP is not a person, so the values are high: behind rootless podman every
browser reaches nginx from the same address (the network gateway), and a campus
often shares one, in which case these are limits on the whole site. If a demo
with many students at once gets 429s on `/api/auth/`, raise `auth_per_ip` first.
The front's own server-side calls go straight to `api:8000`, not through nginx,
so they are not counted.

### Image uploads

A file gets on the server through `POST /uploads/images` only
(`app/api/v1/uploads.py`, helpers in `app/core/uploads.py`). The front sends the
file, gets a path back, and puts *that path* in `image_urls` or `avatar_path`:
the database never holds image data.

- Multipart field `file`, logged in. **413** over `max_upload_bytes` (5 MB),
  **415** if the first bytes are not a PNG, JPEG, GIF or WebP (the file name and
  the `Content-Type` the client sends are ignored), **429** past
  `quota_uploads_per_day` (50) or `rate_uploads_per_hour` (30), **409** past
  `quota_upload_bytes` (100 MB stored per user).
- Stored at `<media_root>/images/<user public_id>/<random>.<ext>` (`media_root`
  is the `media` volume, `/srv/media`), written under a temporary name and moved
  in place, so a half-written file is never served. The answer is
  `{"path": "/media/images/<public_id>/<random>.<ext>"}`; nginx serves it under
  `/media/` (read-only volume).
- One directory per user: the quotas are a scan of it (no table), and deleting a
  user (`DELETE /users/{public_id}`) removes it.
- nginx: `/api/v1/uploads/` alone accepts 6 MB bodies (5 MB plus multipart
  overhead); the rest of `/api/` stays at 64 KB.
- **What an image reference may be** (`is_allowed_image_ref`, checked when a
  listing is created and when `avatar_path` changes): one of the caller's *own*
  uploads, a static asset of the front (`/mock/...`), or an `https` URL on
  `allowed_image_hosts` (the 42 CDN, the same hosts the CSP allows
  for `img-src`). Anything else is a 422, so no `data:` URI, no other user's
  file, no arbitrary host. An avatar the profile form sends back unchanged is
  accepted whatever its shape.
- Every upload is then decoded and re-saved with Pillow (`reencode_image`):
  this confirms the file really is a well-formed image, not just something
  whose first bytes look right, and drops whatever metadata it carried - EXIF
  GPS position on a phone photo, in particular. A JPEG's EXIF orientation is
  baked into the pixels first, so it still looks right once the tag is gone.
  An animated GIF is only decoded frame by frame to check it, then kept as
  received - GIF does not carry EXIF GPS the way a photo does.
- A file uploaded but never attached to a listing or an avatar - the caller
  abandoned the form it was for - is removed by a background loop
  (`purge_orphaned_uploads`, started in `main.py`'s `lifespan`) once it is
  older than `upload_purge_after_seconds` (24h by default), checked every
  `upload_purge_interval_seconds` (1h). It only ever looks at whether the
  file's path is currently held by `listing_images.storage_path` or
  `users.avatar_path` - deliberately not restricted to active listings, so a
  moderator-deleted listing's images (kept on disk on purpose, in case the
  listing is later restored) are never swept up by this.
- **Existing data**: rows written before this hold `data:` URIs in
  `listing_images.storage_path` / `users.avatar_path`; they still display, but
  the profile form would send them back and the API refuses them. In a dev
  database:
  `UPDATE users SET avatar_path = NULL WHERE avatar_path LIKE 'data:%';` and
  `DELETE FROM listing_images WHERE storage_path LIKE 'data:%';` (listings whose
  cover was one show the category placeholder).

---

## Database

### Schema

The entity-relationship diagram is in
[`../schema_design.md`](../schema_design.md). Conventions used throughout
[`models/`](src/app/models/):

- **Keys**: `BIGINT GENERATED ALWAYS AS IDENTITY` primary keys. Users and
  listings also have a `public_id UUID` (`gen_random_uuid()`, from
  `pgcrypto`), which is the only id exposed for them.
- **Case-insensitive text**: `users.email` (unique) and
  `users.display_name` use `CITEXT`.
- **Status columns** are strings with an explicit `CHECK … IN (…)`
  constraint generated from a Python `StrEnum`, not native PostgreSQL enums,
  so adding a value does not need an `ALTER TYPE`.
- **Extensible vocabularies** (`roles`, `listing_conditions`,
  `report_target_types`) are lookup tables. Their rows are reference data,
  seeded by the migration itself, so they also exist in the test and
  production databases.
- **Constraint names** follow a fixed naming convention (`models/base.py`),
  so Alembic autogenerate produces stable names.
- **Integrity in the database**: `CHECK` constraints forbid self-friendship,
  self-block, self-review, a buyer equal to the seller, a negative price, and
  a rating outside 1–5. Unique constraints allow one conversation per buyer
  and listing, one review per author and conversation, and one friend row per
  requester and addressee. The API also refuses a row in the reverse
  direction.
- **`reports.target_id`** is a polymorphic reference with no foreign key. It
  may point at a row that no longer exists.
- **`listings.search_vector`** (`tsvector`, French configuration) is kept up
  to date by the `trg_listings_search_vector` trigger on `title` and `body`.

### Connecting to the database

While the stack runs, open a `psql` shell from the repository root:

```bash
docker compose exec db psql -U "$(cat secrets/POSTGRES_USER)" -d lb42db
```

Under `make dev`, any local client can also connect to `127.0.0.1:5432` with
the user and password from `secrets/POSTGRES_USER` and
`secrets/POSTGRES_PASSWORD`.

### Migrations

There is a single initial migration,
[`bfa429204c94_initial_schema.py`](migrations/versions/bfa429204c94_initial_schema.py).
Most of it is autogenerated. Alembic cannot infer four parts, which are
written by hand outside the generated blocks:

- the `pgcrypto` and `citext` extensions;
- the lookup-table rows;
- the search-vector trigger;
- the `listings.cover_image_id → listing_images.id` foreign key, which is a
  cycle declared with `use_alter`.

Migrations are applied automatically at container start. To apply them by
hand:

```bash
uv run alembic upgrade head        # from backend/, with POSTGRES_* set
```

**To change the schema:**

1. edit the models;
2. generate a revision against a database at `head`:
   `uv run alembic revision --autogenerate -m "short description"`;
3. **review the generated file**: autogenerate misses extensions, triggers,
   data and some constraint changes;
4. run `make test`, which applies every migration to an empty database
   before running the suite.

> [!WARNING]
> `make migrate-fresh` regenerates the initial migration from scratch against
> a throwaway PostgreSQL. It **deletes `migrations/versions/*.py`**, and the
> four hand-written parts listed above must then be restored by hand.

### Demo data

[`seeds.py`](src/app/seeds.py) loads demo data that mirrors the front's mock
files: campuses, categories, users, listings with images, conversations,
friendships, reviews and reports.

- It runs at container start when `SEED_DEMO_DATA=true`: always under
  `make dev`, and under `make up` too, since `.env.example` sets it.
  `make seed_dev` (or `make seed_prod` under `make up`) re-runs it on demand.
- It is **idempotent**: it does nothing if any listing already exists. To
  start over, `make clean` (which deletes the database), then `make dev`.
- It pre-creates the five team accounts (`TEAM_ACCOUNTS`), using the email
  their 42 login will carry, with preset roles: three `admin`, one
  `moderator`, one `user`. They have no password. On the first real login,
  the password-less account is linked instead of a new one being created, so
  the role is kept. This is intended for development databases only.

---

## Developer guide

### Adding an endpoint

A checklist, in the order the work usually happens:

1. **Route.** Add it to the matching module in [`api/v1/`](src/app/api/v1/).
   A new module must be included in
   [`api/v1/__init__.py`](src/app/api/v1/__init__.py) with a tag.
2. **Schemas.** Declare the request and response models in
   [`schemas/`](src/app/schemas/). Type every client-supplied string and id
   with the types from [`schemas/limits.py`](src/app/schemas/limits.py)
   (`PathId`, `DbId`, `BeforeId`, `PageNumber`, the text types), or add a new
   one there.
3. **Access.** Add the right [dependency](#dependencies). For a private
   resource, answer `404` rather than `403` when the caller must not learn
   that it exists.
4. **Abuse.** If users can create rows with it, add a
   [quota](#quotas) (`enforce(...)` before the insert) and, for content other
   people will see, a [rate-limit](#rate-limiting-per-user) bucket in
   `dependencies=[...]`.
5. **Side effects after the commit.** Publish real-time events and analytics
   invalidations only once `session.commit()` has returned.
6. **Tests.** Cover the happy path, validation (`422`), access (`401`,
   `403`, `404`) and every limit it enforces. See [Testing](#testing).
7. **Documentation.** Update the [Endpoint reference](#endpoint-reference) and
   tell the front team when the contract changes.

A template (the `Thing` names are placeholders, not an existing feature):

```python
@router.post("/things", status_code=201, dependencies=[Depends(limit_things)])
async def create_thing(
    payload: ThingCreate,                            # fields typed with schemas/limits.py
    current_user: User = Depends(get_current_user),  # 401 when anonymous
    session: AsyncSession = Depends(get_session),
    hub: Hub = Depends(get_hub),
) -> ThingRead:
    await enforce(                                   # 409 once the user owns too many
        session,
        current_user.id,
        select(func.count()).select_from(Thing).where(Thing.owner_id == current_user.id),
        settings.quota_things,
        "Too many things: delete some first",
    )
    thing = Thing(owner_id=current_user.id, **payload.model_dump())
    session.add(thing)
    await session.commit()

    read = ThingRead.model_validate(thing)
    publish_to_users(hub, "thing.created", (str(current_user.public_id),), read.model_dump(mode="json"))
    analytics_bus.publish("thing.created")           # only if the admin dashboard shows it
    return read
```

> [!NOTE]
> **Route order matters** when paths overlap. `GET /users/me` is declared
> before `GET /users/{public_id}`; the other way round, `me` would be parsed
> as a UUID and answer `422`.

### Publishing events

- **To users' browsers:** `publish_to_users(hub, type, public_ids, payload)`
  from [`realtime_topics.py`](src/app/realtime_topics.py) sends one event on
  each user's `user:<public_id>` topic. Get the hub with
  `hub: Hub = Depends(get_hub)`. A new topic or client message type is
  declared in `realtime_topics.py`; see
  [Declaring a feature](src/app/core/realtime/README.md#declaring-a-feature).
- **To the admin dashboard:** `analytics_bus.publish("<reason>")` from
  [`core/analytics_bus.py`](src/app/core/analytics_bus.py). Add the reason to
  the list in [Server-Sent Events](#server-sent-events-admin-dashboard).

Both must run after the commit, from the event loop (an `async` route).

### Adding a setting

1. Add a typed field with a default to `Settings` in
   [`core/config.py`](src/app/core/config.py). A secret gets no meaningful
   default and is provided through `<NAME>_FILE`.
2. If it must be configurable under Docker, add it to the `api`
   `environment:` block in [`../docker-compose.yml`](../docker-compose.yml)
   (and to `.env.example` if the team should see it).
3. Document it in [Configuration](#configuration).

### Adding a limit

| To add | Do |
|---|---|
| A field limit | Reuse or add a type in `schemas/limits.py`, use it in the request schema, and add the largest accepted value and the first refused one to `tests/test_limits.py` |
| A quota | Add a `quota_*` setting, call `enforce(...)` before the insert, and add a test to `tests/test_quotas.py` |
| A rate limit | Add a `rate_*` setting and a bucket in `ratelimit.py` (`rate_limit(name, setting, window)`), then list it in the route's `dependencies=[...]`. Keep the dependency `async`: a plain `def` would run in a thread pool, and the counters are safe only from the event loop |

### Code quality

From `backend/`:

```bash
uv run ruff check src tests
uv run mypy src
```

Commit messages, branches and reviews follow
[`../CONTRIBUTING.md`](../CONTRIBUTING.md).

---

## Testing

### Running the suite

From the repository root:

```bash
make test
```

This target:

1. starts a throwaway `postgres:18-alpine` container (`lb42_test_db`) on
   `127.0.0.1:5433`, with a database `lebon42_test`;
2. runs `uv run alembic upgrade head` and then `uv run pytest` **on the
   host**, from `backend/`;
3. stops the container, whatever the result.

It never touches the dev or production database, and does not need the stack
to be running. It does need `uv` and Docker (or Podman) on the host.

To run a subset, start a test database the same way (see the `test` target
in the [`Makefile`](../Makefile)), then run:

```bash
cd backend
export POSTGRES_HOST=127.0.0.1 POSTGRES_PORT=5433 \
       POSTGRES_USER=postgres POSTGRES_PASSWORD=postgres POSTGRES_DB=lebon42_test
uv run alembic upgrade head
uv run pytest tests/test_listings.py -k favorite -x
uv run pytest --cov=app --cov-report=term-missing      # coverage report
```

Other targets:

| Command | What it runs |
|---|---|
| `make test_ws` | The real-time core tests (`tests/test_ws`). No database needed |
| `make test_ws_live` | The real-time browser bench on <http://127.0.0.1:8765> (dev only, no authentication). Stop it with `make test_ws_live_shutdown` |
| `make test_auth` | Curl tests of `/api/auth/*` against the running stack. The 42 part is interactive: you log in to the intra in the browser within `AUTH_TIMEOUT` seconds (180 by default). The email/password part needs no one. Set `BASE_URL` to target another host |

### How the tests are built

- **Real PostgreSQL**, never SQLite. The schema relies on `CITEXT`, `JSONB`,
  `gen_random_uuid()`, triggers and PostgreSQL row locks.
- **Isolation**: each test runs inside a transaction that is rolled back at
  the end. The session joins it with savepoints, so the routes' own `commit()`
  calls stay contained.
- **HTTP client**: `client` is an `httpx.AsyncClient` over `ASGITransport`,
  with `get_session` overridden to use that transactional session. No server
  is started.
- **Factories**: `create_user`, `create_listing`, `create_conversation`,
  `create_message`, `create_friend`, `create_review`, `create_report` and
  others, all in [`tests/conftest.py`](tests/conftest.py).
- **Authentication**: `login_as(user)` sets a signed session cookie on the
  client.
- **No network**: the 42 client (`get_ft_client`) is replaced by a fake
  (`fake_ft`), so the whole OAuth flow (state check, account resolution,
  session) runs offline. The real-time hub (`get_hub`) and the user loaders
  (`get_user_loader`, `get_stream_user_loader`) are swappable the same way.
- **Rate limits**: the rate limiter is reset before every test.

### Writing a test

Test names follow `test_<action>_<condition>_<expected_result>`. Cover the
happy path, validation errors and authorization cases for every new route.

```python
async def test_delete_listing_by_another_user_returns_403(
    client, create_user, create_listing, login_as
):
    intruder = await create_user()
    listing = await create_listing()          # owned by a fresh seller
    login_as(intruder)

    response = await client.delete(f"/api/v1/listings/{listing.public_id}")

    assert response.status_code == 403
```

---

## Observability

- **Metrics**: `GET /metrics` in Prometheus format, provided by
  `prometheus-fastapi-instrumentator`.
  - Status codes are not grouped, and unmatched paths are ignored.
  - `/metrics`, `/api/v1/health` and the SSE stream are excluded.
  - The endpoint is reachable only on the internal Docker network: nginx does
    not route it.
- **Prometheus** scrapes `api:8000/metrics` and `postgres-exporter:9187`
  every 15 seconds, and keeps 15 days of data. The alert rules are
  `BackendDown`, `HighHttpErrorRate` (more than 5 % of responses are 5xx over
  1 minute) and `PostgresDown` (see
  [`../monitoring/prometheus/`](../monitoring/prometheus/)). It is not
  exposed: no host port, no nginx route. Grafana is its only client.
- **Grafana** is served under `/grafana/`, with a
  provisioned FastAPI overview dashboard (`fastapi_overview.json`).
- **Logs** go to stdout, stored by Docker's `json-file` driver and capped at
  10 MB per container. Read them with `make logs`, or
  `docker compose logs -f api` for the API alone. The database URL is logged
  only in masked form. OAuth failures are logged with their error code and
  the intra's HTTP status, never the response bodies.

---

## Security summary

| Concern | Measure |
|---|---|
| Secrets | Provided as Docker secrets (files), never written in Compose files or `.env`. `secrets/` is git-ignored. The database password is never logged |
| OAuth login CSRF | Random 256-bit `state` in an HttpOnly cookie scoped to `/api/auth/`, compared in constant time, single use, 10-minute lifetime |
| Open redirect | `next` accepts only same-site paths, and is validated again on the way back |
| Token exposure | The client secret and the intra access token stay server side. The access token is never stored |
| Account takeover | A 42 login never links to an account that has a password |
| Passwords | Hashed with argon2id (`argon2-cffi`), which salts each hash with its own random salt. Never stored or logged in clear. Login answers the same `401`, after the same hashing work, for an unknown email and a wrong password. Checks are rate-limited per email |
| Session theft | `HttpOnly`, `Secure`, `SameSite=Lax` cookie. The JWT carries no role and is signed with a secret generated by `make` |
| CSRF on the API | `SameSite=Lax` cookie, same-origin deployment with CORS disabled, and no state change on `GET` |
| Cross-site WebSocket hijacking | `Origin` allow-list checked before the socket is accepted |
| Enumeration | Users and listings are exposed only by random UUIDs. Private resources answer `404` rather than `403` |
| Privilege changes | The role and account status are read from the database on every request. Sanctions also close open sockets |
| Abuse and oversized input | nginx body cap and per-IP limits, Pydantic field limits, per-user quotas and rate limits |
| Injection | SQLAlchemy parameterised queries only. `LIKE` wildcards are escaped in the admin user search |
| Container | Non-root `appuser`, `no-new-privileges`. The database is not published outside the Docker network in production |
| Transport | TLS 1.2+ at nginx, HTTP redirected to HTTPS, `nosniff`, `Referrer-Policy`, `Permissions-Policy`, and a CSP in production |

---

## Deployment checklist

`make up` on a machine other than your laptop. Go through every item:

- [ ] **Host and ports.** In `.env`, set `SERVER_NAME` to the public host
      name, and `HTTP_PORT` / `HTTPS_PORT` to `80` / `443` if the engine can
      bind them (rootful Docker).
- [ ] **Redirect URI.** Add `FT_REDIRECT_URI=https://<SERVER_NAME>[:<HTTPS_PORT>]/api/auth/callback`
      to `.env`: Compose otherwise passes the localhost URL. Register the same
      URI on the intra.
- [ ] **42 credentials.** `secrets/FT_CLIENT_ID` and `secrets/FT_CLIENT_SECRET`
      are filled in.
- [ ] **Production mode.** Set `ENVIRONMENT=prod` in `.env`, so that a
      missing `SECRET_KEY` stops the API instead of silently using a random
      key.
- [ ] **No demo data.** Set `SEED_DEMO_DATA=false` in `.env` (`.env.example`
      sets `true`) before the first start: the seed creates accounts with the
      `admin` role.
- [ ] **One worker.** `UVICORN_WORKERS` stays `1`.
- [ ] **Monitoring access.** Grafana is public under `/grafana/`, behind its
      own sign-in: `secrets/GRAFANA_USER` (`lb42`) and the random
      `secrets/GRAFANA_PASSWORD` generated by `make`. Keep them, or replace
      them before the first start. Prometheus has no authentication: keep it
      internal, with no host port and no nginx route.
- [ ] **Certificate.** On first start, nginx generates a self-signed
      certificate in the `certs` volume, and reuses any `server.crt` /
      `server.key` it finds there. Put a real certificate there for a public
      host. HSTS is commented out in `nginx.conf`: enable it once the
      certificate is trusted.
- [ ] **Backups.** The database lives in the `pgdata` volume. Back it up;
      `make clean`, `make fclean` and `make re` delete it.

---

## Troubleshooting

**Starting the stack**

| Symptom | Cause | Fix |
|---|---|---|
| The `api` container exits with `FATAL: <NAME>_FILE=... cannot be read` | A secret file is missing or unreadable | Run `make dev` or `make up`, which recreate missing secrets. Check that `secrets/*` are readable (`644`) |
| The `api` container exits with `FATAL: /srv/media cannot be written` | The `media` volume is not writable by the container user, typically because it was created by an image built for another UID | After `make down`, remove it with `docker volume rm lb42_media`. This **deletes every uploaded image** |
| Startup fails with `POSTGRES_PASSWORD is not set` (bare Uvicorn) | Neither `POSTGRES_PASSWORD` nor `POSTGRES_PASSWORD_FILE` is set | Export `POSTGRES_PASSWORD_FILE=../secrets/POSTGRES_PASSWORD`, as in [Without Docker](#without-docker) |
| `make dev` cannot bind `127.0.0.1:5432` | A local PostgreSQL already uses the port | Stop the local server, or change the port mapping in `docker-compose.dev.yml` |
| Rootless Podman cannot bind ports 80 or 443 | Unprivileged ports start at 1024 | Keep `HTTP_PORT=8080` and `HTTPS_PORT=8443`, as in `.env.example` |
| A variable set in `.env` has no effect on the API | Only the variables listed in the `api` `environment:` block reach the container | Add it to that block in `docker-compose.yml` |
| The demo data did not load | The seed runs only when `SEED_DEMO_DATA=true`, and skips a database that already has listings | `make seed_dev` on a dev stack (`make seed_prod` under `make up`). To start from scratch: `make clean`, then `make dev` (**deletes the database**) |

**Signing in**

| Symptom | Cause | Fix |
|---|---|---|
| `GET /api/auth/login` answers `503 42 login is not configured` | `secrets/FT_CLIENT_ID` or `secrets/FT_CLIENT_SECRET` is empty | Fill them in, then restart the stack. See [Registering the application](#registering-the-application) |
| The intra refuses the redirect URI | The URI registered on the intra differs from `FT_REDIRECT_URI` | Make them identical, byte for byte: scheme, `localhost`, port, no trailing slash |
| The browser lands on `/?auth_error=<code>` | The login failed | See the table in [Callback outcomes](#callback-outcomes). `make logs` shows the details |
| Over plain HTTP (bare Uvicorn), the session is not kept and API calls answer `401` | The session cookie is `Secure` by default, and many clients refuse to store or send such a cookie over HTTP | Set `COOKIE_SECURE=false` |
| Sessions are lost every time the API restarts (bare Uvicorn) | No `SECRET_KEY`: a random key is generated per process | Set `SECRET_KEY_FILE=../secrets/SECRET_KEY` |
| I need a moderator or admin account in development | New accounts are `user`, and only an admin can change a role | After your first login, run `docker compose exec db psql -U "$(cat secrets/POSTGRES_USER)" -d lb42db -c "UPDATE users SET role = 'admin' WHERE display_name = '<your login>';"` (your display name, if you changed it). The change applies at once. **Development databases only** |

**Using the API**

| Symptom | Cause | Fix |
|---|---|---|
| Swagger UI is blank under `make up` | The production CSP blocks its CDN scripts | Use `make dev`, or load `/api/openapi.json` in any OpenAPI client |
| `429` with a `Retry-After` header | A rate limit: per IP in nginx (always `Retry-After: 1`), or per user in the API (usually longer) | Wait. Per IP, common behind rootless Podman or a shared campus IP: raise the zone in `nginx.conf`, `auth_per_ip` first. Per user: raise the `RATE_*` setting, see [Rate limiting](#rate-limiting-per-user) |
| `409`, or `429` without `Retry-After`, with a message such as "Too many active listings…" or "This conversation is full" | A quota | Delete something (`409`) or wait up to 24 hours (`429`). See [Quotas](#quotas) |
| The WebSocket handshake answers `403` | Foreign or missing `Origin`, or no valid session | Serve the front from the allowed origin, or set `WS_ALLOWED_ORIGINS`. Check `/api/v1/users/me` for the session |
| The WebSocket closes with `4001` | Logout, suspension, removal, deletion, or the JWT expired | Check `/api/v1/users/me`: sign in again if it answers `204`, otherwise reconnect |
| Real-time events reach only some clients | More than one Uvicorn worker | Keep `UVICORN_WORKERS=1` |

---

## Known limitations

- **One worker only** (`UVICORN_WORKERS=1`). Rate-limit counters, the
  WebSocket hub, the analytics bus and the presence tracker live in process
  memory. Several workers would each hold their own copy. Scaling out would
  need a shared backend, such as Redis, behind these components. Their state
  is also lost on restart.
- **Stateless sessions**: there is no server-side revocation list. See
  [Session](#session).
- **Images** live in the `media` volume, one directory per user, with no
  table: the upload quotas scan that directory. See
  [Image uploads](#image-uploads).
- **Search** uses `ILIKE` on the title and body. `search_vector` is kept up to
  date but not yet queried, and has no index.
- **Unread counts**: `unread_count` in conversation summaries is always `0`,
  because no read tracking exists yet.
- **The schema is ahead of the API.** These exist in the database but are not
  used by any route yet:
  - `saved_searches`;
  - two-factor columns (`totp_*`);
  - `users.locale`;
  - `users.email_verified_at` for email/password accounts (no confirmation
    mail is sent);
  - `listings.view_count` (never incremented);
  - `listings.published_at` and `listings.expires_at` (never set; no
    expiration job);
  - `listing_images.width`, `listing_images.height` and
    `listing_images.phash`;
  - `edited_at` on messages and reviews (no edit endpoints).
- **Moderation**:
  - restoring a listing always makes it `active`;
  - direct messages cannot be reported;
  - reopening with `unblock_user` does not apply the sanction hierarchy.
- **Presence** does not take blocks into account.
- **Client handling of `429`**: only the sign-in forms and message sending
  read `Retry-After`; elsewhere `fetchApi` throws with the `detail` message,
  which the page displays.
- **Swagger UI under `make up`** is blocked by the production CSP. See
  [Service URLs](#service-urls).

---

## Glossary

| Term | Meaning |
|---|---|
| **Intra** | The 42 intranet, which acts as the OAuth2 provider |
| **`public_id`** | The random UUID that identifies a user or a listing in the API. The internal integer key is never exposed |
| **Principal** | The identity of a WebSocket connection: the user's `public_id`, as a string |
| **Topic** | A real-time channel that sessions subscribe to, such as `user:<public_id>` or `presence` |
| **Soft delete** | The row is kept and marked with `deleted_at` (and `status = deleted` for listings). It can be restored |
| **Suspension** | `is_active = false`. The account can no longer use the API, but nothing is deleted |
| **Sanction** | A suspension or a removal decided by moderation, subject to the [sanction hierarchy](#sanction-hierarchy) |
| **Posted listing** | A listing that is neither a draft nor deleted |
| **Stock** | Listings that are `active` or `sold`, and not deleted. Used by the analytics and the personal statistics |
| **Quota** | A cap on how many rows a user can own or create (`409` or `429`) |
| **Rate limit** | A cap on how many requests a user or an IP can send per window (`429`) |
