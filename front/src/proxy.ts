import { NextResponse, type NextRequest } from 'next/server';
import { getApiBaseUrl } from '@/lib/api/client';
import type { UserRole } from '@/types/user';

// Pages refused before they are rendered unless the backend accepts the
// session. roles null: any logged-in user. AuthGuard / RoleGuard still run in
// the browser for client-side navigations; the API checks every data route.
const PROTECTED: { path: string; roles: UserRole[] | null }[] = [
  { path: '/profile', roles: null },
  { path: '/messages', roles: null },
  { path: '/listings/create', roles: null },
  { path: '/moderation', roles: ['moderator', 'admin'] },
  { path: '/analytics', roles: ['admin'] },
];

// Built on request.nextUrl, so same origin as the request: Next sends it as a
// relative Location. Behind nginx that origin is not the one the browser
// used, so an absolute URL would send it astray.
function redirectTo(request: NextRequest, pathname: string, search = ''): NextResponse {
  const url = request.nextUrl.clone();
  url.pathname = pathname;
  url.search = search;
  return NextResponse.redirect(url, 307);
}

function toLogin(request: NextRequest): NextResponse {
  const { pathname, search } = request.nextUrl;
  // Not straight to the intra: an email account has no 42 login. The page
  // offers both ways in and brings the browser back here.
  return redirectTo(request, '/login', `?next=${encodeURIComponent(pathname + search)}`);
}

export async function proxy(request: NextRequest): Promise<NextResponse> {
  const { pathname } = request.nextUrl;
  const rule = PROTECTED.find((r) => pathname === r.path || pathname.startsWith(`${r.path}/`));
  if (!rule) return NextResponse.next();

  const session = request.cookies.get('session')?.value;
  if (!session) return toLogin(request);

  // The backend decides: the JWT is never read here.
  let response: Response;
  try {
    response = await fetch(`${getApiBaseUrl()}/auth/me`, {
      headers: { Cookie: `session=${session}` },
      cache: 'no-store',
    });
  } catch {
    return new NextResponse('Service indisponible', { status: 503 });
  }
  // expired, tampered with, or the account is disabled
  if (response.status === 401) return toLogin(request);
  // fail closed: an API error is not a reason to serve the page
  if (!response.ok) return new NextResponse('Service indisponible', { status: 503 });

  const me: { role: UserRole } = await response.json();
  if (rule.roles && !rule.roles.includes(me.role)) return redirectTo(request, '/');
  return NextResponse.next();
}

export const config = {
  matcher: [
    {
      source: '/(profile|messages|moderation|analytics)/:path*',
      // Link prefetches (hovering the Header) are not checked: each one would
      // cost an /auth/me call, and a logged-out one a redirect to /login.
      missing: [
        { type: 'header', key: 'next-router-prefetch' },
        { type: 'header', key: 'purpose', value: 'prefetch' },
      ],
    },
    {
      source: '/listings/create',
      missing: [
        { type: 'header', key: 'next-router-prefetch' },
        { type: 'header', key: 'purpose', value: 'prefetch' },
      ],
    },
  ],
};
