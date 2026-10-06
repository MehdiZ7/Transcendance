// Server side (SSR, server actions): straight to the api container.
// Browser: same origin, nginx proxies /api/v1.
// The realtime socket does not go through here: lib/realtime targets /api/ws.
export function getApiBaseUrl(): string {
  if (typeof window === 'undefined') {
    if (process.env.API_INTERNAL_URL) {
      return process.env.API_INTERNAL_URL.replace(/\/+$/, '');
    }
    const publicUrl = process.env.NEXT_PUBLIC_API_URL;
    if (publicUrl && (publicUrl.startsWith('http://') || publicUrl.startsWith('https://'))) {
      return publicUrl.replace(/\/+$/, '');
    }
    return 'http://127.0.0.1:8000/api/v1';
  }

  const clientUrl = process.env.NEXT_PUBLIC_API_URL ?? '/api/v1';
  return clientUrl.replace(/\/+$/, '');
}

// Error class for API errors carrying the HTTP status
export class ApiError extends Error {
  status: number;
  retryAfter?: number;

  constructor(status: number, message: string, retryAfter?: number) {
    super(message);
    this.name = 'ApiError';
    this.status = status;
    this.retryAfter = retryAfter;
  }
}

// An error response as an ApiError carrying the API's `detail` and Retry-After.
// Exported for the calls outside /api/v1 (lib/api/auth.ts).
export async function toApiError(response: Response, endpoint: string): Promise<ApiError> {
  let detail = `Erreur API: ${response.status} sur ${endpoint}`;
  let retryAfter: number | undefined;
  const retryHeader = response.headers.get('Retry-After');
  if (retryHeader) {
    const parsed = parseInt(retryHeader, 10);
    if (!Number.isNaN(parsed)) {
      retryAfter = parsed;
    }
  }

  try {
    const body = await response.json();
    if (typeof body === 'string') {
      detail = body;
    } else if (body && typeof body === 'object') {
      if (Array.isArray(body.detail)) {
        detail = body.detail
          .map((err: { msg?: string; loc?: string[] }) => err.msg || JSON.stringify(err))
          .join(', ');
      } else {
        detail = body.detail ?? body.message ?? detail;
        if (typeof detail === 'object') {
          detail = JSON.stringify(detail);
        }
      }
    }
  } catch {
    // The body is not JSON or is empty
  }
  return new ApiError(response.status, detail, retryAfter);
}

export async function fetchApi<T>(endpoint: string, options: RequestInit = {}): Promise<T> {
  const baseUrl = getApiBaseUrl();
  const normalizedEndpoint = endpoint.startsWith('/') ? endpoint : `/${endpoint}`;
  const url = `${baseUrl}${normalizedEndpoint}`;

  const isFormData = typeof FormData !== 'undefined' && options.body instanceof FormData;
  const headers = new Headers(options.headers);
  if (!isFormData && !headers.has('Content-Type')) {
    headers.set('Content-Type', 'application/json');
  }

  if (typeof window === 'undefined' && !headers.has('Cookie')) {
    const { cookies } = await import('next/headers');
    const session = (await cookies()).get('session');
    if (session) {
      headers.set('Cookie', `session=${session.value}`);
    }
  }

  const response = await fetch(url, {
    ...options,
    headers,
    credentials: 'include',
  });

  if (response.status === 204) return undefined as T;

  if (!response.ok) throw await toApiError(response, endpoint);

  return response.json() as Promise<T>;
}
