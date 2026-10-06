# Le Bon 42 — Frontend Technical & Architecture Guide (`DEV_DOC.md`)

This document serves as the **core technical reference** for the entire **Le Bon 42** frontend. It details the code architecture, implementation choices, communication protocols, API contracts, real-time lifecycle, and best practices for developing and extending the codebase.

---

## Table of Contents

1. [Overview & Architectural Principles](#1-overview--architectural-principles)
2. [Framework Architecture (Next.js 16 App Router)](#2-framework-architecture-nextjs-16-app-router)
3. [Security, Authentication & Authorization (RBAC)](#3-security-authentication--authorization-rbac)
4. [Data Access Layer & HTTP Client (`src/lib/api/`)](#4-data-access-layer--http-client-srclibapi)
5. [Real-Time, WebSockets & Server-Sent Events](#5-real-time-websockets--server-sent-events)
6. [Domain Hooks & Complex State Management](#6-domain-hooks--complex-state-management)
7. [Data Model & TypeScript Typing (`src/types/`)](#7-data-model--typescript-typing-srctypes)
8. [Design System, UI & Styles (Tailwind CSS v4)](#8-design-system-ui--styles-tailwind-css-v4)
9. [End-to-End Testing Strategy (Playwright)](#9-end-to-end-testing-strategy-playwright)
10. [Development Guides & Best Practices](#10-development-guides--best-practices)

---

## 1. Overview & Architectural Principles

The **Le Bon 42** frontend provides a smooth, reactive, and secure user experience while enforcing a strict separation of concerns.

### Architectural Pillars:

1. **Server-First by Default**: 
   - Publicly accessible pages (Catalog `/`, Listing Detail `/listings/[public_id]`, Legal pages `/privacy`, `/terms`, `/browsers`) leverage **Server-Side Rendering (SSR)** for optimal SEO, instantaneous initial page loads, and dynamic OpenGraph metadata generation.
2. **Client-Driven for Rich Interactivity**:
   - Highly interactive application views (Real-time Messaging `/messages`, Moderation Queue `/moderation`, Interactive Profile `/profile`, Live Analytics `/analytics`) are built as Client Components with dedicated domain hooks.
3. **End-to-End Strict Typing**:
   - Zero usage of the `any` type. All data models exchanged with the REST API and WebSocket frames are strictly typed under `src/types/`.
4. **Decoupled Network Layer**:
   - React components never perform raw `fetch()` calls. All requests route through dedicated domain modules in `src/lib/api/`, ensuring reusability, consistent error handling, and transparency across client and server environments.
5. **Resilience & "Fail-Closed"**:
   - Security takes precedence: on network failure or backend downtime, protected routes are locked down rather than inadvertently leaking unauthorized views.

---

## 2. Framework Architecture (Next.js 16 App Router)

The project runs on **Next.js 16.3.8** using the **App Router**, configured in `standalone` output mode for lightweight containerization.

### 2.1. Server Components vs Client Components

| Component Type | Directive | Project Usage | Example Files |
|---|---|---|---|
| **Server Component** | Default (no directive) | Content pages, initial data fetching, SEO, metadata generation | `app/(main)/page.tsx`, `app/(main)/listings/[public_id]/page.tsx`, `app/(main)/browsers/page.tsx` |
| **Client Component** | `"use client"` at top of file | Stateful UI (`useState`, `useEffect`), event handlers, WebSockets, React contexts | `components/messages/ChatWindow.tsx`, `components/moderation/UsersTable.tsx`, `components/listings/FilterBar.tsx` |

### 2.2. Server Actions: Listing Creation

Publishing a listing (`/listings/create`) uses a dedicated Next.js **Server Action**: [`createListingAction`](src/app/(main)/listings/create/actions.ts).

```typescript
// src/app/(main)/listings/create/actions.ts
'use server';

import { revalidatePath } from 'next/cache';
import { redirect } from 'next/navigation';
import { listingsApi } from '@/lib/api/listings';
import { catalogApi } from '@/lib/api/catalog';
import { getDefaultImageForCategory } from '@/lib/images';
import { isObjectCategory } from '@/lib/categories';

export async function createListingAction(
  prevState: { error: string | null } | undefined,
  formData: FormData
) {
  const title = (formData.get('title') as string) || '';
  const price = Number(formData.get('price')) || 0;
  // ... Field extraction, validation, category resolution ...
  try {
    const newListing = await listingsApi.create({ ... });
    revalidatePath('/');
    redirect(`/listings/${newListing.public_id}`);
  } catch (err) {
    return { error: err instanceof Error ? err.message : 'Error creating listing' };
  }
}
```

**Key Server Action Characteristics:**
- Runs exclusively on the Node.js server upon form submission.
- Uses `revalidatePath('/')` to purge the home page cache so the newly created item appears immediately in the feed.
- Uses `redirect(...)` to issue a native HTTP 303 redirect to the created listing's URL.
- Request body limits for Server Actions are raised to 8 MB in `next.config.ts` (`serverActions: { bodySizeLimit: "8mb" }`). Images no longer go through the action: [`ImageUploadDropzone`](src/components/listings/ImageUploadDropzone.tsx) uploads the file to `POST /uploads/images` first, and the form sends only the returned `/media/...` path.

### 2.3. Routing & Security Proxy: `src/proxy.ts`

In Next.js 16, server-side route interception and redirection is handled in [`src/proxy.ts`](src/proxy.ts).

```typescript
// src/proxy.ts
import { NextResponse, type NextRequest } from 'next/server';
import { getApiBaseUrl } from '@/lib/api/client';
import type { UserRole } from '@/types/user';

const PROTECTED: { path: string; roles: UserRole[] | null }[] = [
  { path: '/profile', roles: null },
  { path: '/messages', roles: null },
  { path: '/listings/create', roles: null },
  { path: '/moderation', roles: ['moderator', 'admin'] },
  { path: '/analytics', roles: ['admin'] },
];

export async function proxy(request: NextRequest): Promise<NextResponse> {
  const { pathname } = request.nextUrl;
  const rule = PROTECTED.find((r) => pathname === r.path || pathname.startsWith(`${r.path}/`));
  if (!rule) return NextResponse.next();

  const session = request.cookies.get('session')?.value;
  if (!session) return toLogin(request);

  // Authoritative backend validation (JWT is never decoded locally on the proxy)
  let response: Response;
  try {
    response = await fetch(`${getApiBaseUrl()}/auth/me`, {
      headers: { Cookie: `session=${session}` },
      cache: 'no-store',
    });
  } catch {
    return new NextResponse('Service indisponible', { status: 503 });
  }

  if (response.status === 401) return toLogin(request);
  if (!response.ok) return new NextResponse('Service indisponible', { status: 503 });

  const me: { role: UserRole } = await response.json();
  if (rule.roles && !rule.roles.includes(me.role)) return redirectTo(request, '/');
  return NextResponse.next();
}
```

#### Critical Rules in `src/proxy.ts`:
1. **Authoritative Backend Validation**: The frontend never attempts to decrypt or locally verify JWT signatures. It queries `/auth/me` with the forwarded session cookie.
2. **Fail-Closed**: If the backend returns a 500 status code or times out, the proxy returns a 503 status code without admitting unauthorized visitors into protected routes.
3. **Prefetch Shielding**: The `config.matcher` in `proxy.ts` ignores requests with `next-router-prefetch` or `purpose: prefetch` headers. Otherwise every link hovered in the header would cost an `/auth/me` call, and a logged-out one a redirect to `/login`.
4. **Login Redirect**: an anonymous visitor goes to `/login?next=<page>`, not straight to the intra: an email/password account has no 42 login, and the page offers both.

---

## 3. Security, Authentication & Authorization (RBAC)

### 3.1. Authentication Lifecycle

Both ways in are offered by [`AuthForm`](src/components/auth/AuthForm.tsx), shown in [`AuthModal`](src/components/auth/AuthModal.tsx) and on the `/login` page. API calls live in [`src/lib/api/auth.ts`](src/lib/api/auth.ts) (`authApi`).

**42 OAuth:**

1. The browser navigates (never `fetch`) to `/api/auth/login?next=<page>`. The API stores a random `state` in an HttpOnly cookie and redirects to `https://api.intra.42.fr/oauth/authorize`.
2. The student approves access on the intra, which redirects back to `/api/auth/callback?code=...&state=...`.
3. The backend exchanges the code for a 42 access token, retrieves the user identity (persistent 42 numeric ID), creates or updates the user record, and signs a session JWT stored in the HTTP `session` cookie.
4. The browser lands back on the application (`next`, or `POST_LOGIN_REDIRECT`). A failure lands on `/?auth_error=<code>`.

**Email and password:**

1. `AuthForm` validates the fields in the browser (email format, password length from `lib/limits.ts`, display name), then calls `authApi` (`POST /api/auth/register` or `POST /api/auth/login`) through `AuthModalContext`.
2. On success, the API sets the same `session` cookie, and the browser does a full navigation to `next` (or the current page), which resets the `useCurrentUser` cache.
3. `authErrorMessage` turns each error status into a French message; for a `429`, it says how long to wait, from `Retry-After`.
4. The profile page's [`PasswordForm`](src/components/profile/PasswordForm.tsx) sets or changes the password (`POST /api/auth/password`).

### 3.2. Client-Side Authentication Cache (`useCurrentUser.ts`)

To avoid hammering the backend on multiple concurrent component mounts, [`src/hooks/useCurrentUser.ts`](src/hooks/useCurrentUser.ts) implements an **in-flight shared promise cache** at module scope:

```typescript
// src/hooks/useCurrentUser.ts
type UserCache =
  | { status: "idle" }
  | { status: "loading"; promise: Promise<UserProfile | null> }
  | { status: "ready"; user: UserProfile | null }
  | { status: "error" };

let cache: UserCache = { status: "idle" };

function loadCurrentUser(): Promise<UserProfile | null> {
  if (cache.status === "ready") return Promise.resolve(cache.user);
  if (cache.status === "loading") return cache.promise;

  const promise = usersApi
    .getCurrent()
    .then((me) => {
      cache = { status: "ready", user: me };
      return me;
    })
    .catch((err) => {
      // an error (network, 5xx) is not "anonymous" (anonymous is a 204 -> null):
      // do not cache a definitive null, keep it retryable on the next mount
      cache = { status: "error" };
      throw err;
    });

  cache = { status: "loading", promise };
  return promise;
}
```

**Why this pattern?**
When multiple components (e.g. the `Header` and a page `AuthGuard`) mount concurrently, they share the exact same pending promise. The first component to trigger the network request resolves data for all consumers, eliminating hydration races and preventing UI freezing on loading skeletons.

**Anonymous vs. error.** Anonymous is a successful `204` (`getCurrent()` returns `null`, cached as `ready`). A network/5xx failure is a distinct `error` state: it is never cached as a logged-out user, so a transient outage does not falsely sign the user out. The hook returns `{ user, role, isLoading, isError, refresh, logout }`; `refresh()` drops the cache and retries `/users/me`.

### 3.3. Client Guard Components

- **[`AuthGuard`](src/components/auth/AuthGuard.tsx)**: Ensures the current user is authenticated. If anonymous, opens [`AuthModal`](src/components/auth/AuthModal.tsx) and redirects to `/`.
- **[`RoleGuard`](src/components/auth/RoleGuard.tsx)**: Verifies that the user's role (`user?.role`) is in the allowed list (`allowed: UserRole[]`). Unauthorized users are immediately redirected home.

---

## 4. Data Access Layer & HTTP Client (`src/lib/api/`)

All HTTP interactions with the backend are centralized under `src/lib/api/`.

### 4.1. Universal HTTP Engine: `src/lib/api/client.ts`

[`src/lib/api/client.ts`](src/lib/api/client.ts) exports the foundational `fetchApi<T>()` utility function.

#### Base URL Resolution (`getApiBaseUrl`):
- **Server-Side (Node.js)**: If `API_INTERNAL_URL` is set (Docker Compose), requests target `http://api:8000/api/v1` over the internal container network.
- **Client-Side (Browser)**: Uses `NEXT_PUBLIC_API_URL` (default: `/api/v1`), proxied same-origin by Nginx.

#### Transparent Cookie Forwarding in SSR:
During SSR, the browser cannot attach cookies automatically to internal API calls. `fetchApi` uses Next.js `cookies()` (`next/headers`) to extract the `session` cookie and forward it:

```typescript
if (typeof window === 'undefined' && !headers.has('Cookie')) {
  const { cookies } = await import('next/headers');
  const session = (await cookies()).get('session');
  if (session) {
    headers.set('Cookie', `session=${session.value}`);
  }
}
```

#### Error Handling (`ApiError`):
If the HTTP status is not 2xx (excluding 204), `fetchApi` extracts error details from the response JSON (FastAPI `detail` format or Pydantic validation arrays) and throws an `ApiError(status, message)`.

---

### 4.2. API Modules by Domain

#### Catalog (`catalogApi` — [`src/lib/api/catalog.ts`](src/lib/api/catalog.ts))
| Method | Route | Description |
|---|---|---|
| `getCategories()` | `GET /categories` | Fetches the complete category hierarchy |
| `getLocations()` | `GET /locations` | Lists available 42 campuses for listings |

#### Listings (`listingsApi` — [`src/lib/api/listings.ts`](src/lib/api/listings.ts))
| Method | Route | Description |
|---|---|---|
| `getAll(params)` | `GET /listings?...` | Paginated search. Takes `q`, `category`, `location`, `min_price`, `max_price`, `sort`, sent as the API's `q`, `categorie`, `location`, `prix_min`, `prix_max`, `sort` |
| `getByPublicId(publicId)` | `GET /listings/{public_id}` | Full listing detail (or `null` if 404) |
| `getByUser(userId)` | `GET /users/{userId}/listings` | Listings published by a user |
| `getFavoritesByUser(userId)`| `GET /users/{userId}/favorites`| Listings favorited by a user |
| `create(data)` | `POST /listings` | Creates a new listing |
| `addFavorite(listingId)` | `POST /listings/{id}/favorite` | Adds listing to favorites |
| `removeFavorite(listingId)` | `DELETE /listings/{id}/favorite` | Removes listing from favorites |
| `delete(listingId)` | `DELETE /listings/{id}` | Deletes a listing (owner only; moderators go through a report) |
| `markSold(listingId)` | `POST /listings/{id}/mark-sold` | Marks listing as sold |

#### Messaging (`conversationsApi` & `messagesApi` — [`src/lib/api/messages.ts`](src/lib/api/messages.ts))
| Method | Route | Description |
|---|---|---|
| `conversationsApi.list()` | `GET /conversations` | Lists current user's listing conversations |
| `conversationsApi.getOrCreateListing(listingId)` | `POST /conversations/listing` | Opens or retrieves a listing conversation |
| `conversationsApi.markAsSold(conversationId)` | `POST /conversations/{id}/mark-sold` | Marks item sold to the other participant |
| `messagesApi.list(convId, beforeId)` | `GET /conversations/{id}/messages` | Lists messages with ascending pagination via `before_id` |
| `messagesApi.send(convId, body)` | `POST /conversations/{id}/messages` | Sends a message in a listing conversation |

#### Friends & Direct Chat (`friendsApi` — [`src/lib/api/friends.ts`](src/lib/api/friends.ts))
| Method | Route | Description |
|---|---|---|
| `list(userId)` | `GET /users/{userId}/friends` | Lists accepted friends for a user |
| `listPending()` | `GET /friends/pending` | Lists incoming pending friend requests |
| `listConversations()` | `GET /friends/messages` | Lists direct friend conversation threads |
| `listMessages(friendPublicId, beforeId)` | `GET /friends/{public_id}/messages` | Messages exchanged with a friend (paginated) |
| `sendMessage(friendPublicId, body)` | `POST /friends/{public_id}/messages` | Sends a private message to a friend |
| `sendRequest(userId)` | `POST /friends` | Sends a friend request (`{ user_id }`) |
| `cancelRequest(userId)` | `DELETE /friends/requests/{userId}` | Cancels an outgoing friend request |
| `accept(requestId)` | `POST /friends/{id}/accept` | Accepts an incoming friend request |
| `decline(requestId)` | `POST /friends/{id}/decline` | Declines an incoming friend request |
| `remove(userId)` | `DELETE /friends/{userId}` | Removes a friend from friendship list |

#### Users & Administration (`usersApi` — [`src/lib/api/users.ts`](src/lib/api/users.ts))
| Method | Route | Description |
|---|---|---|
| `getCurrent()` | `GET /users/me` | Current user profile (`null` if anonymous) |
| `getByRef(ref)` | `GET /users/{public_id}` | Public profile of a user |
| `getMyStats()` | `GET /users/me/stats` | Sales revenue, spending, and category distribution |
| `update(data)` | `PATCH /users/me` | Updates profile (`display_name`, `bio`, `avatar_path`, `location_id`) |
| `block(userId)` | `POST /users/{userId}/block` | Blocks a user |
| `unblock(userId)` | `DELETE /users/{userId}/block` | Unblocks a user |
| `getBlocked()` | `GET /users/me/blocks` | Lists blocked users |
| `listUsers(params)` | `GET /users?...` | Paginated user management list (`admin` only) |
| `updateUserRole(publicId, role)` | `PATCH /users/{public_id}/role` | Updates user role (`user`, `moderator`, `admin`) |
| `deleteUser(publicId)` | `DELETE /users/{public_id}` | Irreversible user deletion with cascade |

#### Moderation & Reports (`reportsApi` — [`src/lib/api/reports.ts`](src/lib/api/reports.ts))
| Method | Route | Description |
|---|---|---|
| `getAll()` | `GET /reports` | Lists all platform reports (`moderator`/`admin`) |
| `create(data)` | `POST /reports` | Submits a report (`listing`, `message`, `user`, `review`) |
| `reject(reportId)` | `POST /reports/{id}/reject` | Rejects report without taking action |
| `deleteTarget(reportId, type, id)` | `POST /reports/{id}/resolve` | Resolves report by deleting content (`delete_target`) |
| `blockUser(reportId, userId)` | `POST /reports/{id}/resolve` | Resolves report by suspending user (`block_user`) |
| `reopen(reportId)` | `POST /reports/{id}/reopen` | Reopens a closed/resolved report |
| `unblockUser(reportId, userId)` | `POST /reports/{id}/reopen` | Reopens report and unsuspends user |

#### Reviews (`reviewsApi` — [`src/lib/api/reviews.ts`](src/lib/api/reviews.ts))
| Method | Route | Description |
|---|---|---|
| `listByUser(userId)` | `GET /users/{userId}/reviews` | Fetches reviews received by a user |
| `create(data)` | `POST /reviews` | Submits rating (1-5) and review for a completed transaction |
| `delete(reviewId)` | `DELETE /reviews/{id}` | Deletes a review the current user wrote |

#### Authentication (`authApi` — [`src/lib/api/auth.ts`](src/lib/api/auth.ts))
| Method | Route | Description |
|---|---|---|
| `register(input)` | `POST /api/auth/register` | Creates an email/password account and opens the session |
| `login(input)` | `POST /api/auth/login` | Email/password login |
| `changePassword(input)` | `POST /api/auth/password` | Sets or changes the password |

These routes live under `/api/auth`, outside `/api/v1`. The 42 login is a navigation to `/api/auth/login`, not an API call.

#### Uploads (`uploadsApi` — [`src/lib/api/uploads.ts`](src/lib/api/uploads.ts))
| Method | Route | Description |
|---|---|---|
| `uploadImage(file)` | `POST /uploads/images` | Uploads one image (multipart) and returns its `/media/...` path, for a listing or an avatar |

#### Analytics (`analyticsApi` — [`src/lib/api/analytics.ts`](src/lib/api/analytics.ts))
Exposes calls to `/analytics/*`: `getOnlineStudents()`, `getListingsToday()`, `getPendingReports()`, `getSoldPercentage()`, `getCategoryDistribution()`, `getListingsBetweenDates(start, end)`, `getTotalListingsValue()`, `getAverageListingPrice()`, and `getTopLikedListings()`.

---

### 4.3. Backend Error → Frontend Handling Matrix

Every backend route, its HTTP error codes, and how `ApiError` (see 4.1) is turned into UI feedback for it.

#### Listings (`/listings`)

| Method & Route | HTTP Status | Backend Reason / Message | Frontend File & Handling | User Rendering |
| :--- | :--- | :--- | :--- | :--- |
| `POST /listings` | **401**<br>**404**<br>**404**<br>**422** | Not authenticated<br>`Category not found`<br>`Location not found`<br>Pydantic field validation | `front/src/app/(main)/listings/create/actions.ts`<br>`front/src/app/(main)/listings/create/page.tsx` | Red alert banner displayed above the creation form via `useActionState`. |
| `GET /listings/{id}` | **404** | `Listing not found` | `front/src/lib/api/listings.ts` (`getByPublicId`)<br>`front/src/app/(main)/listings/[public_id]/page.tsx` | Triggers `notFound()`, rendering the application's 404 page. |
| `DELETE /listings/{id}` | **401**<br>**403**<br>**404**<br>**409** | Not authenticated<br>`Only the seller can delete this listing`<br>`Listing not found`<br>`Cannot delete a sold listing` | `front/src/components/listings/DeleteListingButton.tsx` | Red error message displayed directly inside the deletion confirmation modal. |
| `POST /listings/{id}/mark-sold` | **401**<br>**403**<br>**404**<br>**409** | Not authenticated<br>`Only the seller can mark this listing as sold`<br>`Listing not found`<br>`Listing is not active` | `front/src/components/listings/MarkSoldListingButton.tsx` | Error message displayed inside the confirmation modal. |
| `POST/DELETE /listings/{id}/favorite` | **401**<br>**404** | Not authenticated<br>`Listing not found` | `front/src/components/listings/FavoriteButton.tsx` | If 401: opens authentication modal.<br>If network/backend error: optimistic rollback of heart state and count. |

#### Messaging & Conversations (`/conversations`)

| Method & Route | HTTP Status | Backend Reason / Message | Frontend File & Handling | User Rendering |
| :--- | :--- | :--- | :--- | :--- |
| `POST /conversations/listing` | **400**<br>**401**<br>**403**<br>**404** | `Cannot start a conversation with yourself`<br>Not authenticated<br>`Cannot message a blocked user`<br>`Listing not found` | `front/src/hooks/useMessages.ts`<br>`front/src/components/messages/ChatWindow.tsx`<br>`front/src/app/(main)/messages/page.tsx` | Red alert banner displayed in the chat window explaining why the conversation cannot be opened. |
| `POST /conversations/{id}/messages` | **401**<br>**403**<br>**404**<br>**409** | Not authenticated<br>`Cannot message a blocked user`<br>`Conversation not found`<br>`Conversation is closed` | `front/src/hooks/useMessages.ts`<br>`front/src/components/messages/ChatWindow.tsx` | Unsent text is restored into the input field to prevent loss, and a red error banner appears above the input. |
| `POST /conversations/{id}/mark-sold` | **403**<br>**404**<br>**409** | `Only the seller can mark a listing as sold`<br>`Listing not found`<br>`Listing is not active` | `front/src/hooks/useMessages.ts`<br>`front/src/components/messages/TransactionBanner.tsx` | Red error message displayed on the conversation's transaction banner. |
| `GET /conversations/{id}/messages` | **404** | `Conversation not found` | `front/src/hooks/useMessages.ts` | Pagination error caught in `loadMoreError` with an explicit label under the "Load more" button. |

#### Friends & Profiles (`/friends`, `/users`)

| Method & Route | HTTP Status | Backend Reason / Message | Frontend File & Handling | User Rendering |
| :--- | :--- | :--- | :--- | :--- |
| `POST /friends` | **400**<br>**403**<br>**404**<br>**409** | `Cannot send a friend request to yourself`<br>`Cannot send a friend request to a blocked user`<br>`User not found`<br>`A friend request already exists between these users` | `front/src/components/profile/FriendShipActionButton.tsx` | Red error text rendered immediately below the friend action button. |
| `POST /friends/{id}/accept`<br>`POST /friends/{id}/decline` | **404**<br>**409** | `Friend request not found`<br>`Friend request is not pending` | `front/src/components/profile/FriendShipActionButton.tsx`<br>`front/src/hooks/useProfile.ts` | Error text under the button and red alert banner on the profile page (`actionError`). |
| `DELETE /friends/{id}` | **404** | `User not found` / `Friendship not found` | `front/src/hooks/useProfile.ts`<br>`front/src/components/profile/FriendShipActionButton.tsx` | Red alert banner on the profile page. |
| `POST/DELETE /users/{id}/block` | **400**<br>**404** | `Cannot block yourself`<br>`User not found` | `front/src/hooks/useProfile.ts`<br>`front/src/app/(main)/profile/page.tsx` | Red alert banner on the profile page (`actionError`). |
| `PATCH /users/me` | **404**<br>**422** | `Location not found`<br>Format validation errors (bio, display name, etc.) | `front/src/hooks/useProfile.ts` | Error message displayed inside the profile edit modal. |
| `GET /users/{id}` | **404** | `User not found` | `front/src/app/(main)/profile/page.tsx` | Triggers `notFound()`, rendering the Next.js 404 page. |

#### Reviews (`/reviews`)

| Method & Route | HTTP Status | Backend Reason / Message | Frontend File & Handling | User Rendering |
| :--- | :--- | :--- | :--- | :--- |
| `POST /reviews` | **400**<br>**400**<br>**400**<br>**403**<br>**404**<br>**409** | `Cannot review yourself`<br>`Subject must be the other participant...`<br>`Listing must be marked as sold via this conversation...`<br>`Not a participant in this conversation`<br>`Subject not found` / `Conversation not found`<br>`You already reviewed this conversation` | `front/src/components/reviews/ReviewModal.tsx` | Detailed red error message displayed directly inside the review modal. |

#### Moderation & Reports (`/reports`)

| Method & Route | HTTP Status | Backend Reason / Message | Frontend File & Handling | User Rendering |
| :--- | :--- | :--- | :--- | :--- |
| `POST /reports` | **400**<br>**404**<br>**409** | `Cannot report yourself`<br>`Report target not found`<br>`You already have an open report on this target` | `front/src/components/ui/ReportModal.tsx` | Red error message displayed inside the report modal. |
| `POST /reports/{id}/resolve`<br>`POST /reports/{id}/reject`<br>`POST /reports/{id}/reopen` | **400**<br>**403**<br>**404**<br>**409** | `Cannot suspend yourself`<br>`Only an admin can suspend a moderator or admin`<br>`Report not found` / `User not found`<br>`Report already closed` / `Report is not closed` | `front/src/hooks/useModeration.ts` | Red alert Toast notification at the bottom of the screen with the exact backend message. |

#### Account Administration (`/users` admin)

| Method & Route | HTTP Status | Backend Reason / Message | Frontend File & Handling | User Rendering |
| :--- | :--- | :--- | :--- | :--- |
| `PATCH /users/{id}/role` | **400**<br>**403**<br>**404**<br>**422** | `Cannot change your own role`<br>`Admin access required`<br>`User not found`<br>`Unknown role` | `front/src/components/moderation/UsersTable.tsx` | Toast notification reporting role update failure. |
| `DELETE /users/{id}` | **400**<br>**403**<br>**404** | `Cannot delete yourself`<br>`Admin access required`<br>`User not found` | `front/src/components/moderation/UsersTable.tsx` | Toast notification reporting deletion failure. |

#### Analytics (`/analytics/*`)

| Method & Route | HTTP Status | Backend Reason / Message | Frontend File & Handling | User Rendering |
| :--- | :--- | :--- | :--- | :--- |
| `GET /analytics/listings-between-dates` | **422** | `Range cannot exceed 366 days` | `front/src/components/analytics/ListingsBetweenDatesChart.tsx` | Red error box with explanation and "Retry" button. |
| All analytics queries | **500** / unavailable | Server errors or timeout | All analytics components (`CategoryPieChart`, `QuickStatsBar`, etc.) | Each chart features an isolated error state with a "Retry" button. |

Every method of `src/lib/api/` maps to an existing backend route.

---

## 5. Real-Time, WebSockets & Server-Sent Events

The frontend combines two real-time technologies based on directionality requirements.

### 5.1. WebSocket Client (`src/lib/realtime/`)

Real-time state is orchestrated by a singleton [`RealtimeClient`](src/lib/realtime/client.ts) instance per tab, accessible via `getRealtime()`.

```
                    ┌───────────────────────────────┐
                    │        RealtimeClient         │
                    │       (ws://.../api/ws)       │
                    └───────┬───────────────┬───────┘
                            │               │
                 Topic      │               │ Topic
            user:<public_id>│               │ presence
                            ▼               ▼
                 ┌──────────────────┐   ┌──────────────────┐
                 │ useMessages      │   │ presenceSource   │
                 │ - message.created│   │ - snapshot       │
                 │ - typing         │   │ - changed        │
                 └──────────────────┘   └──────────────────┘
```

#### Lifecycle & States:
The connection transitions through: `idle` ➔ `connecting` ➔ `open` ➔ `reconnecting` ➔ `unauthorized` / `replaced` / `closed`.

| Close Code | Cause | Client Action |
|---|---|---|
| `1001`, `1006`, `1011`, `1012`, `1013` | Network failure, server restart, server capacity | Reconnects with **exponential backoff** (0.5s to 30s) and jitter, sends `resume` frame |
| `4000` | Session taken over by another tab | Sets state to `replaced` and stops (prevents socket stealing loops) |
| `4001` | Session expired, logged out, or account suspended | Queries `/users/me`. Anything but `200` (anonymous is `204`): sets `unauthorized` and halts; a page load after login creates a new client. `200`: reconnects with a fresh stream |
| `1008` | No initial frame within 10s | Halts in `unauthorized` |
| No message in 50s | Dead connection | Socket considered dead, closed, and reconnect initiated |
| Regular pings | Heartbeat | Client dispatches an application `ping` every 25 seconds |

#### Supported Topics:
1. **`user:<public_id>`** (Restricted to account owner):
   - `message.created`: New message in a listing conversation (received by both participants).
   - `typing`: Counterparty is typing (`{ conversation_id, user_id, is_typing }`).
   - `friend_message.created`: New direct friend message.
   - `friend_typing`: Friend is typing (`{ friend_id, user_id, is_typing }`).
2. **`presence`** (Open to all authenticated users):
   - `presence.snapshot`: Full list of online user IDs upon subscription (`{ online: string[] }`).
   - `presence.changed`: Emitted when a user opens their first or closes their last socket (`{ user_id, status: "online" | "offline" }`).

#### Synchronization Golden Rule:
> [!IMPORTANT]
> **Initial state is ALWAYS fetched via HTTP REST**. Real-time streams only deliver deltas. Mutations (sending messages, marking items sold) route through the REST API, guaranteeing database commitment before WebSocket event broadcast.

---

### 5.2. Server-Sent Events Stream (`AnalyticsLiveContext.tsx`)

The admin dashboard (`/analytics`) consumes the SSE stream `/api/v1/analytics/stream`:
- `connected` event: confirms connection and triggers initial refresh.
- `analytics_update` event: emitted on platform mutations (new listing, report, sale). The context applies a **500ms debounce** before incrementing `refreshTrigger`, avoiding request storms during bulk operations.
- Fallback polling at 60s: keeps metrics fresh that don't trigger events (active student count, daily peak).

---

## 6. Domain Hooks & Complex State Management

### 6.1. `useMessages` (`src/hooks/useMessages.ts`)
Encapsulates unified messaging across listing and friend conversation models:
- **Unique Thread Keying**: Prefixes IDs to prevent collisions: `"listing:<id>"` vs `"friend:<id>"`.
- **Smart Typing Indicators**: Emits `is_typing: true` at most every 1.5s, reverts to `false` after 2s idle. Counterparty visual indicator auto-clears after 5s.
- **Infinite Pagination**: `handleLoadMore` fetches older history using the oldest message's ID (`before_id`).
- **Transaction Integration**: Coordinates `handleMarkAsSold` and `handleReviewSubmitted` to update thread UI states.

### 6.2. `useProfile` (`src/hooks/useProfile.ts`)
Manages profile workflows:
- Evaluates whether the active view belongs to the logged-in user (`isOwnProfile`).
- Executes a resilient `Promise.all` loading profile, listings, reviews, favorites, friends, and block status concurrently.
- Implements the friendship state machine: `null` ➔ `pending` ➔ `accepted` ➔ `blocked`.
- Loads financial stats (`MyStats`) for the earnings and spending overview.

### 6.3. `useModeration` (`src/hooks/useModeration.ts`)
Drives the moderation queue:
- Handles tab selection across 6 queues (`listings`, `messages`, `users`, `reviews`, `history`, `admin-users`).
- Dynamically counts badge totals (`ModerationCounts`).
- Controls action modals (`ModerationModals`): report rejection, content deletion, account suspension/reopening.

---

## 7. Data Model & TypeScript Typing (`src/types/`)

### User Entities ([`src/types/user.ts`](src/types/user.ts))
```typescript
export type UserRole = 'admin' | 'moderator' | 'user';

export interface PublicUser {
  id: string;
  public_id: string;
  display_name: string;
  role: UserRole;
  avatar_path?: string | null;
  bio?: string | null;
  rating: number;
  rating_count: number;
  is_active?: boolean;
}

export interface UserProfile extends PublicUser {
  email?: string;
  locale?: string;
  created_at?: string;
  listings_count?: number;
  liked_listings_count?: number;
  friends_count?: number;
  reviews_count?: number;
  reviews?: Review[];
  recent_listings?: Listing[];
  liked_listings?: Listing[];
  friends?: PublicUser[];
  has_blocked_me?: boolean;
  has_password?: boolean;
}
```

### Listing Entities ([`src/types/listing.ts`](src/types/listing.ts))
```typescript
export type ListingCondition = 'new' | 'like_new' | 'good' | 'fair' | 'for_parts';
export type ListingStatus = 'draft' | 'active' | 'sold' | 'expired' | 'archived' | 'deleted';

export interface Listing {
  id: string;
  public_id: string;
  seller_id: string;
  category_id: string;
  title: string;
  body: string | null;
  price: number;
  currency?: string;
  condition?: ListingCondition | null;
  attributes?: Record<string, unknown> | null;
  location_id: string;
  status: ListingStatus;
  view_count: number;
  created_at: string;
  seller?: PublicUser;
  buyer_id?: string | null;
  buyer?: PublicUser;
  category?: Category;
  location?: Location;
  images?: ListingImage[];
  favorites_count?: number;
  is_favorited?: boolean;
}
```

### Messaging Entities ([`src/types/message.ts`](src/types/message.ts))
```typescript
export type InboxKind = 'listing' | 'friend';

export interface InboxConversation extends ConversationSummary {
  kind: InboxKind;
  rawId: string;
}

export interface Message {
  id: string;
  conversation_id: string;
  sender_id: string;
  body: string;
  created_at: string;
  edited_at?: string | null;
  deleted_at?: string | null;
  sender?: PublicUser;
}
```

---

## 8. Design System, UI & Styles (Tailwind CSS v4)

The project leverages the **Tailwind CSS v4** syntax configured in [`src/app/globals.css`](src/app/globals.css).

### 8.1. 42 Theme Tokens (`@theme`)

```css
@theme {
  /* 42 Visual Identity & Marketplace */
  --color-brand-42: #00babc;
  --color-brand-42-light: #26e5e8;
  --color-brand-42-dark: #009698;
  --color-brand-42-glow: rgba(0, 186, 188, 0.25);

  --color-accent-coral: #ff5e36;
  --color-accent-coral-hover: #eb4e27;
  --color-accent-amber: #f59e0b;
  --color-accent-emerald: #10b981;
  --color-accent-indigo: #6366f1;

  /* Surfaces & Slate Shades */
  --color-surface-base: #f8fafc;
  --color-surface-card: #ffffff;
  --color-surface-muted: #f1f5f9;
  --color-slate-850: #131c2e;
  --color-slate-925: #0a0f1d;
  --color-slate-950: #050811;
}
```

### 8.2. Custom Utilities
- `.glass`, `.glass-dark`, `.glass-cyan`: Glassmorphic styling using `backdrop-filter: blur()`.
- `.text-gradient-42`: Signature 42 cyan gradient text.
- `.card-premium`: Elevated cards with subtle hover highlights.
- `.shimmer-loading`: Sweep animation for skeleton loaders.

### 8.3. Reusable UI Components (`src/components/ui/`)
- **[`Button`](src/components/ui/Button.tsx)**: Polymorphic component rendering as `<button>` or Next.js `<Link>` if `href` is supplied. Handles variants (`primary`, `secondary`, `outline`, `ghost`, `danger`), loading spinners (`isLoading`), and disabled states.
- **[`Modal`](src/components/ui/Modal.tsx)**: Accessible modal with background scroll lock, Escape key/backdrop click dismissal, and React Portals.
- **[`Badge`](src/components/ui/Badge.tsx)**: Visual status badges (`default`, `admin`, `moderator`, `success`, `closed`, `warning`).
- **[`Avatar`](src/components/ui/Avatar.tsx)**: Displays profile image or generates stylized gradient initials.
- **[`Pagination`](src/components/ui/Pagination.tsx)**: Numbered pagination bar with truncation ellipses for large collections.

### 8.4. Universal Image Resolution (`src/lib/images.ts`)
The `getImageUrl(storagePath, categoryId)` function transparently resolves:
1. Uploaded files served by nginx under `/media/...` (listing images and avatars).
2. Complete remote URLs (`https://`, such as 42 profile pictures).
3. Local relative paths served by Next.js (`/mock/...`).
4. Vector placeholders per category (`getDefaultImageForCategory`) when there is no image.
5. `data:` and `blob:` URLs, kept only for rows stored before real uploads existed.

`isUnoptimizedImage(url)` tells `<Image />` to skip Next.js's optimizer for `/media/` files (Next cannot fetch them from nginx), SVGs, and `data:`/`blob:` URLs.

---

## 9. End-to-End Testing Strategy (Playwright)

Automated E2E tests live under `front/e2e/` configured via [`playwright.config.ts`](playwright.config.ts).

### 9.1. Authentication Forgery (`e2e/global.setup.ts`)

A 42 OAuth login cannot be automated, and the seeded team accounts have no password. To test fully authenticated flows:

1. `global.setup.ts` reads each seeded account's `public_id` from the running dev database (`docker compose exec db psql`), so `make dev` must be up:
   - `admin` (`mzouhir@student.42.fr`)
   - `moderator` (`flomulle@student.42.fr`)
   - `user` (`lmilando@student.42.fr`)
   - `demo` (`iargence@student.42.fr`, also an admin)
2. Signs authentic HS256 JWT cookies using `secrets/SECRET_KEY`.
3. Saves storage state contexts to `.auth/<name>.json`.
4. Playwright test projects inject the relevant file into their `storageState`.

`auth-password.spec.ts` does not use them: it signs up its own email/password accounts.

### 9.2. Test Suite Coverage

| Spec File | Scenarios & Scope |
|---|---|
| `smoke.spec.ts` | Validates error-free page loads across `/`, `/messages`, `/profile`, `/moderation`, `/analytics`, `/listings/create`, `/privacy`, `/terms` |
| `navigation.spec.ts` | Checks role-conditional navigation links and mobile menu responsiveness |
| `listings.spec.ts` | Text queries, campus filters, advanced filter modal, filter reset |
| `listing-detail.spec.ts`| Listing rendering, favorite toggle, report modal display |
| `listing-create.spec.ts`| End-to-end listing creation flow and redirect to new item |
| `messages.spec.ts` | Conversation rendering, message dispatch, and thread updates |
| `profile.spec.ts` | Profile tabs, in-place info editing, friendship interactions |
| `moderation.spec.ts` | RBAC gatekeeping (rejection of regular users) and queue traversal for staff |
| `analytics.spec.ts` | Admin RBAC gatekeeping and Recharts dashboard rendering |
| `multi-user.spec.ts` | Concurrency test with two distinct user sessions in isolated contexts |
| `legal.spec.ts` | Footer links to legal notices, privacy policy, and terms of service |
| `auth-password.spec.ts` | Email/password sign-up and login, field validation, protected-page redirect and return, refused registration, hostile `next`, password change |

Per-spec test counts and the latest results per browser are in [`BROWSERS.md`](BROWSERS.md).

---

## 10. Development Guides & Best Practices

### 10.1. Adding a New Page

1. Create directory and route file under `src/app/(main)/my-page/page.tsx`.
2. If the page requires authentication or a role:
   - Add the rule to the `PROTECTED` array in [`src/proxy.ts`](src/proxy.ts):
     ```typescript
     { path: '/my-page', roles: ['admin'] }
     ```
   - Ensure the path is matched in `src/proxy.ts` `config.matcher`.
   - Wrap the component with [`AuthGuard`](src/components/auth/AuthGuard.tsx) or [`RoleGuard`](src/components/auth/RoleGuard.tsx).
3. If linked in navigation, append entry to `NAV_ITEMS` in [`src/components/layout/Header.tsx`](src/components/layout/Header.tsx).

### 10.2. Adding a New API Endpoint

1. Define request and response TypeScript interfaces under `src/types/`.
2. Add the method to the corresponding module in `src/lib/api/`:
   ```typescript
   export const myApi = {
     async getItem(id: string): Promise<MyItem> {
       return fetchApi<MyItem>(`/my-endpoint/${id}`);
     },
   };
   ```
3. Call the method inside your component or hook with clean `isLoading` and `error` state handling.

### 10.3. Listening to a New WebSocket Event

1. Define the event payload type in [`src/lib/realtime/topics.ts`](src/lib/realtime/topics.ts).
2. In your Client Component, consume `useRealtimeTopic`:
   ```typescript
   useRealtimeTopic<MyPayload>(
     userTopic(currentUser.public_id),
     (event) => {
       if (event.type === 'my_new_event') {
         // Process payload and update state
       }
     }
   );
   ```

### 10.4. Contribution Guidelines

- **Always verify before committing**: run `npm run lint` and `npx playwright test --project=chromium`.
- **No inline styles**: exclusively use Tailwind CSS v4 utility classes.
- **Optimized images**: use Next.js `<Image />`, with `unoptimized={isUnoptimizedImage(url)}` for uploads, SVGs and `data:` URLs.
- **Accessibility**: ensure interactive buttons include descriptive text or `aria-label`, and inputs provide associated labels.
