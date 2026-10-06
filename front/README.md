# Le Bon 42 — Frontend (`front/`)

Modern, reactive, and secure web interface for the **Le Bon 42** platform — the community marketplace and mutual aid platform dedicated to 42 students (listings, real-time messaging, friend management, transaction reviews, moderation, and analytics dashboard).

The frontend is built with **Next.js 16 (App Router)** in **TypeScript**, styled with **Tailwind CSS v4**, and tested end-to-end with **Playwright**.

---

## Table of Contents

- [Tech Stack Overview](#tech-stack-overview)
- [Architecture & Global Integration](#architecture--global-integration)
- [Project Structure](#project-structure)
- [Quick Start](#quick-start)
- [Features & Application Pages](#features--application-pages)
- [Authentication & Access Control (RBAC)](#authentication--access-control-rbac)
- [Real-Time & Live Data](#real-time--live-data)
- [E2E Testing & Quality](#e2e-testing--quality)
- [Containerization & Deployment](#containerization--deployment)
- [Additional Documentation](#additional-documentation)

---

## Tech Stack Overview

| Domain | Technologies & Tools | Role |
|---|---|---|
| **Framework** | [Next.js 16.3.8](https://nextjs.org/) (App Router, `standalone`) | Hybrid rendering (SSR, Client Components, Server Actions), routing |
| **UI Library** | [React 19.2.8](https://react.dev/) & React DOM 19 | Reactive components, Hooks, Suspense, Transitions |
| **Language** | [TypeScript 5](https://www.typescriptlang.org/) | Strict static typing across the entire codebase |
| **Styles** | [Tailwind CSS v4](https://tailwindcss.com/) (`@tailwindcss/postcss`) | Custom 42 design system, `@theme` tokens, utility classes |
| **Visualization** | [Recharts 2.15](https://recharts.org/) | Charts (donuts, bar charts, line curves) for Analytics & User Profile |
| **Real-Time** | Native WebSockets (`/api/ws`) & SSE (`/api/v1/analytics/stream`) | Instant messaging, user presence tracking, live dashboard |
| **E2E Testing** | [Playwright 1.63](https://playwright.dev/) | Cross-browser mock-free tests (Chromium, Firefox, WebKit) |
| **Linter** | ESLint 9 (`eslint-config-next`) | Static analysis and code quality |
| **Container** | Docker (Node 22 Alpine, multi-stage) | Isolated development and production runtime environments |

---

## Architecture & Global Integration

The frontend application integrates into Le Bon 42's distributed architecture orchestrated by Docker Compose:

```
                                  Client Browser
                                         │
                                HTTPS :8443 / TLS
                                         ▼
                            ┌────────────────────────┐
                            │      Nginx Proxy       │
                            └────┬──────────────┬────┘
                                 │              │
                    / and assets │              │  /api/ (REST)
                     Next.js     │              │  /api/ws (WebSocket)
                                 ▼              ▼
                     ┌───────────────┐   ┌───────────────┐
                     │   Front-End   │   │   Back-End    │
                     │  Next.js 16   │──▶│    FastAPI    │
                     │  (Port 3000)  │   │  (Port 8000)  │
                     └───────────────┘   └───────┬───────┘
                        SSR via internal         │
                        API URL                  ▼
                                         ┌───────────────┐
                                         │  PostgreSQL   │
                                         └───────────────┘
```

### Communication Rules:
1. **External Access**: The client browser exclusively communicates with the Nginx reverse proxy on `https://localhost:8443`.
2. **Same-Origin**: The frontend is served on `/` and the API on `/api/`. Therefore, no CORS restrictions occur during standard usage.
3. **Server-Side Rendering (SSR / Server Actions)**: The Next.js container queries the API internally via `http://api:8000/api/v1` (configured via `API_INTERNAL_URL`).
4. **Browser (CSR)**: Client-side code issues relative requests (`/api/v1`) using `NEXT_PUBLIC_API_URL`.
5. **Real-Time (WebSockets)**: A single WebSocket connection per browser tab is opened to `/api/ws` reusing the existing HTTP session cookie.

---

## Project Structure

The `front/` directory follows the Next.js 16 App Router architectural guidelines:

```text
front/
├── e2e/                             # Playwright end-to-end test suite (12 specs)
│   ├── global.setup.ts              # Session generation (admin, moderator, user, demo)
│   ├── helpers.ts                   # Test and navigation utilities
│   └── *.spec.ts                    # Domain-specific test files
├── public/                          # Static assets served directly
│   └── mock/placeholders/           # Styled category SVG placeholders
├── src/
│   ├── app/                         # Next.js App Router (pages, layouts, actions)
│   │   ├── (main)/                  # Route group sharing the main layout
│   │   │   ├── page.tsx             # Home: listing catalog with real-time filters
│   │   │   ├── listings/
│   │   │   │   ├── [public_id]/     # Listing detail (SSR + dynamic metadata)
│   │   │   │   └── create/          # Listing creation (Server Action + Dropzone)
│   │   │   ├── messages/            # Inbox and unified real-time chat
│   │   │   ├── profile/             # Self-profile and public profile (/profile/[public_id])
│   │   │   ├── moderation/          # Moderation queue and account management
│   │   │   ├── analytics/           # Global statistics dashboard (admin only)
│   │   │   ├── browsers/            # Browser compatibility page
│   │   │   ├── login/               # Sign-in page (42 or email/password), target of protected-page redirects
│   │   │   ├── privacy/             # Privacy Policy (GDPR)
│   │   │   └── terms/               # Terms of Service
│   │   ├── globals.css              # Tailwind CSS v4 theme, visual effects, print styles
│   │   ├── error.tsx                # Route-level error boundary
│   │   ├── global-error.tsx         # Root error boundary
│   │   └── layout.tsx               # Root layout (Header, Footer, Auth modal)
│   ├── components/                  # Modular React components
│   │   ├── analytics/               # Dashboard components (KPIs, Recharts charts, PDF export)
│   │   ├── auth/                    # Sign-in modal and form (42 or email/password), route guards (AuthGuard, RoleGuard)
│   │   ├── layout/                  # Dynamic header navigation and footer
│   │   ├── legal/                   # Shared presentation component for legal pages
│   │   ├── listings/                # Listing cards, search bar, filters, dropzone
│   │   ├── messages/                # Chat window, message bubbles, transaction banner
│   │   ├── moderation/              # Moderation tabs, report cards, users table
│   │   ├── profile/                 # Friendship actions, personal buying/selling stats
│   │   ├── reviews/                 # Review submission modal and buttons
│   │   └── ui/                      # Atomic reusable UI components (Button, Modal, etc.)
│   ├── context/                     # React contexts (AuthModalContext, AnalyticsLiveContext)
│   ├── hooks/                       # Custom business hooks (useCurrentUser, useMessages, etc.)
│   ├── lib/
│   │   ├── api/                     # HTTP abstraction layer (fetchApi, domain modules)
│   │   ├── realtime/                # Real-time WebSocket client, reconnection manager, topics
│   │   ├── categories.ts            # Category definitions and dynamic attributes logic
│   │   ├── images.ts                # Image resolver (SVG placeholders, 42 avatars, uploads under /media/)
│   │   └── utils.ts                 # Tailwind class merging utility (`cn`)
│   ├── types/                       # Centralized TypeScript definitions (users, listings, etc.)
│   └── proxy.ts                     # Next.js 16 Proxy (server-side route protection)
├── Dockerfile                       # Multi-stage build (development & standalone production)
├── Dockerfile.e2e                   # Containerized image to run Playwright WebKit
├── package.json                     # Dependencies and npm scripts
├── playwright.config.ts             # E2E test suite configuration
├── tsconfig.json                    # TypeScript configuration
├── BROWSERS.md                      # Browser compatibility matrix and E2E results
├── DOCKER.md                        # Frontend Docker documentation
└── DEV_DOC.md                       # Comprehensive technical developer guide
```

---

## Quick Start

### 1. Via Docker Compose (Recommended)

The frontend is preconfigured to run with the database, FastAPI, and Nginx:

```bash
# At the root of the transcendence repository
make dev        # Starts the full stack in development mode with hot reloading
```

The application is immediately accessible at: **`https://localhost:8443`**.

### 2. Standalone Mode (Local Node.js)

To work exclusively on the UI using local Node.js:

```bash
cd front

# Install dependencies
npm install

# Start the Next.js development server (port 3000)
npm run dev
```

> [!NOTE]
> In standalone mode on port 3000, Nginx is bypassed, and the default relative `/api/v1` would reach Next.js itself. Set `NEXT_PUBLIC_API_URL=http://localhost:8000/api/v1`, and run the API outside Docker (see [Without Docker](../backend/README.md#without-docker)) with `CORS_ORIGINS=http://localhost:3000`. The WebSocket still targets `/api/ws` on the page's own host, so real-time features need the full stack.

### Environment Variables

| Variable | Default Value | Description |
|---|---|---|
| `NEXT_PUBLIC_API_URL` | `/api/v1` | API endpoint prefix for requests issued from the browser |
| `API_INTERNAL_URL` | `http://api:8000/api/v1` | Internal URL used by the Node.js server during Server-Side Rendering (SSR) |
| `PLAYWRIGHT_BASE_URL` | `https://localhost:8443` | Target base URL for running Playwright tests |

---

## Features & Application Pages

### 1. Catalog and Listings (`/`, `/listings/[public_id]`, `/listings/create`)
- **Home (`/`)**: Grid display with dynamic pagination, text search, category selection, 42 campus location filtering, price bounds, and five sort orders (newest, oldest, price ascending, price descending, most liked).
- **Listing Detail (`/listings/[public_id]`)**: Full SSR with OpenGraph/SEO dynamic metadata, item condition display (`new`, `like new`, `good condition`, etc.), instant favorite button, seller profile link, report modal, and direct conversation trigger.
- **Listing Creation (`/listings/create`)**: Adaptive interactive form according to the selected category (conditional physical vs non-physical fields), immediate image preview upload, and Next.js Server Action validation with error display.

### 2. Unified Real-Time Messaging (`/messages`)
- **Unified Inbox**: Gathers both listing-related negotiations and direct friend-to-friend conversations in a single view.
- **Real-Time Experience**: Instant message delivery via WebSockets, typing indicator (*"typing..."* with 2-second timeout), and smooth pagination for message histories via `before_id`.
- **Complete Sale Lifecycle (Transaction Banner)**: Enables the seller to mark an item as sold to the current buyer, then prompts the buyer to leave a 1-to-5 star rating and comment.

### 3. User Profiles & Relations (`/profile`, `/profile/[public_id]`)
- **Viewing & Editing**: Displays active listings, favorited items, and received reviews. In-place editing of display name, biography, and avatar.
- **Personal Dashboard (`UserStatsDashboard`)**: Backend-computed metrics (total sales revenue, purchase volume, average item price, category donut charts).
- **Friendship & Safety**: Send, accept, or decline friend requests, view active friends with live presence dots, and block/unblock users.

### 4. Moderation & Administration (`/moderation`)
- **Multi-Category Queue**: Grouping of open reports by target type (*listings*, *messages*, *users*, *reviews*).
- **Fast Moderator Actions**: Reject unfounded reports, delete offending items, or suspend reported accounts.
- **Full History**: Audit trail of resolved or closed reports with status filters and reopening capability.
- **User Account Management (Admin)**: Full user table with search, pagination, role modification (`user`, `moderator`, `admin`), and cascading deletion.

### 5. Analytics Dashboard (`/analytics`)
- **Live SSE Updates**: Connects to the `/api/v1/analytics/stream` Server-Sent Events stream to update metrics on platform events without manual reloads.
- **Key Performance Indicators (KPIs)**: Connected students, listings created today, pending reports, percentage of sold items, total inventory value.
- **Data Visualizations**: Publication volume curve across selected date ranges, category distribution, and top-liked listings leaderboard.
- **PDF Export**: Print-ready A4 portrait layout (`@media print`) that removes navigation elements and optimizes contrast.

### 6. Legal & Compatibility Pages (`/privacy`, `/terms`, `/browsers`)
- **Supported Browsers (`/browsers`)**: Documentation certifying full support across Chrome, Firefox, and Safari.
- **Privacy Policy (`/privacy`)** & **Terms of Service (`/terms`)**: Clear presentation of community rules and GDPR-compliant data processing terms.

---

## Authentication & Access Control (RBAC)

Two ways to sign in, both offered by [`AuthModal`](src/components/auth/AuthModal.tsx) and the `/login` page ([`AuthForm`](src/components/auth/AuthForm.tsx)):

- **42 OAuth2**: the browser is sent to the intra through `GET /api/auth/login?next=<page>`, and comes back through the API's callback.
- **Email and password**: the form posts to `POST /api/auth/register` or `POST /api/auth/login`. Fields are validated in the browser first, then again by the API.

Either way:

1. The API sets a signed `session` cookie (an HS256 JWT; `HttpOnly`, `SameSite=Lax`, `Secure`). The front never reads it.
2. **Server-Side Verification ([`src/proxy.ts`](src/proxy.ts))**: before a protected page is rendered, the Next.js server checks the cookie against `GET /api/v1/auth/me`. Without a valid session, the user is redirected to `/login?next=<page>`; with the wrong role, to `/`. An API error answers `503` rather than serving the page.
3. **Client-Side Verification (`AuthGuard` and `RoleGuard`)**: the same rules during client-side navigation, without a full page reload.

### Access Control Matrix

| Route | Anonymous Visitor | User (`user`) | Moderator (`moderator`) | Administrator (`admin`) |
|---|:---:|:---:|:---:|:---:|
| `/` (Catalog) | ✅ Public Access | ✅ Allowed | ✅ Allowed | ✅ Allowed |
| `/listings/[public_id]` | ✅ Read-only | ✅ Read + Actions | ✅ Read + Actions | ✅ Read + Actions |
| `/listings/create` | ❌ Redirect to Login | ✅ Allowed | ✅ Allowed | ✅ Allowed |
| `/messages` | ❌ Redirect to Login | ✅ Allowed | ✅ Allowed | ✅ Allowed |
| `/profile` | ❌ Redirect to Login | ✅ Allowed | ✅ Allowed | ✅ Allowed |
| `/profile/[public_id]` | ❌ Redirect to Login | ✅ Allowed | ✅ Allowed | ✅ Allowed |
| `/moderation` | ❌ Redirect to Login | ❌ Redirect to Home | ✅ Allowed | ✅ Allowed |
| `/analytics` | ❌ Redirect to Login | ❌ Redirect to Home | ❌ Redirect to Home | ✅ Allowed |
| `/login`, `/privacy`, `/terms`, `/browsers` | ✅ Public Access | ✅ Allowed | ✅ Allowed | ✅ Allowed |

"Redirect to Login" means `/login?next=<page>`, which brings the user back after signing in.

---

## Real-Time & Live Data

The frontend implements two complementary protocols depending on data freshness requirements:

```
                  ┌──────────────────────┐
                  │       Browser        │
                  └───┬──────────────┬───┘
                      │              │
      WebSocket       │              │  Server-Sent Events
      /api/ws         │              │  /analytics/stream
                      ▼              ▼
           ┌────────────────┐   ┌────────────────┐
           │   Messaging    │   │   Analytics    │
           │       &        │   │   Live         │
           │    Presence    │   │   Dashboard    │
           └────────────────┘   └────────────────┘
```

1. **WebSockets (`src/lib/realtime/`)**:
   - Single connection per tab to `/api/ws`.
   - Automatic reconnect with exponential backoff (0.5s to 30s) and stream resumption (`resume`).
   - Dynamic topics:
     - `user:<public_id>`: incoming messages (`message.created`, `friend_message.created`) and typing events (`typing`, `friend_typing`).
     - `presence`: synchronizes user online status (`presence.snapshot`, `presence.changed`).
2. **Server-Sent Events (`AnalyticsLiveContext`)**:
   - Listens to the unidirectional `/api/v1/analytics/stream` stream.
   - Listens for `analytics_update` events with a 500ms debounce to refresh dashboard metrics without overwhelming the backend.

---

## E2E Testing & Quality

The frontend is verified with an automated end-to-end test suite built on **Playwright 1.63**:

```bash
# Run all tests on Chromium
npx playwright test --project=chromium

# Run with verbose test list
npx playwright test --reporter=list

# Open interactive HTML test report
npm run test:e2e:report
```

### Suite Features:
- **No Mocks**: Tests run against the actual development stack (`make dev`) connected to a live database.
- **Multi-Role Sessions**: [`e2e/global.setup.ts`](e2e/global.setup.ts) forges valid session cookies for the seeded `admin`, `moderator`, `user` and `demo` accounts, without an interactive 42 OAuth flow. `auth-password.spec.ts` signs up its own email/password accounts.
- **Cross-Browser Verification**: Validated across **Chromium**, **Firefox**, and **WebKit** (Safari).

For detailed compatibility results and instructions on running WebKit via Docker, refer to [`BROWSERS.md`](BROWSERS.md).

---

## Containerization & Deployment

The [`Dockerfile`](Dockerfile) uses an optimized multi-stage build on Alpine Linux:

- `base`: `node:22-alpine3.24`, sets working directory, and disables Next.js telemetry.
- `dependencies`: Deterministic installation using `npm ci`.
- `development`: Lightweight image with bind-mount support for hot reloading (`npm run dev`).
- `builder`: Production compilation (`npm run build`).
- `production`: Ultra-lightweight standalone image copying only `.next/standalone`, public assets, and running under a non-root `nextjs` user (UID 1001).

For further container build and execution commands, see [`DOCKER.md`](DOCKER.md).

---

## Additional Documentation

- 📖 **[`DEV_DOC.md`](DEV_DOC.md)**: **In-depth technical developer documentation** (detailed architecture, complete API modules reference, WebSocket lifecycle, custom hooks, and contribution guidelines).
- 🌐 **[`BROWSERS.md`](BROWSERS.md)**: Complete cross-browser compatibility matrix and Playwright test specifications.
- 🐳 **[`DOCKER.md`](DOCKER.md)**: Docker build stages and container execution manual.
- ⚡ **[`src/lib/realtime/README.md`](src/lib/realtime/README.md)**: Client WebSocket protocol specification and real-time event handling.
- ⚙️ **[`../backend/README.md`](../backend/README.md)**: Backend FastAPI documentation and 42 OAuth flow details.
