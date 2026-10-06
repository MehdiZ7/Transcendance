import type { ChangePasswordInput, PasswordLoginInput, RegisterInput } from "@/types/auth";
import { MAX_PASSWORD_LENGTH, MIN_PASSWORD_LENGTH } from "@/lib/limits";
import { ApiError, toApiError } from "./client";

// /api/auth/*, outside the /api/v1 base of fetchApi. Browser only and always
// same origin (nginx), like the 42 login and the logout: the response sets
// the session cookie.
async function postAuth(path: string, body: unknown): Promise<void> {
  const response = await fetch(`/api/auth${path}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    credentials: "same-origin",
    body: JSON.stringify(body),
  });
  if (!response.ok) throw await toApiError(response, path);
}

export const authApi = {
  register(input: RegisterInput): Promise<void> {
    return postAuth("/register", input);
  },

  login(input: PasswordLoginInput): Promise<void> {
    return postAuth("/login", input);
  },

  changePassword(input: ChangePasswordInput): Promise<void> {
    return postAuth("/password", input);
  },
};

export type AuthAction = "login" | "register" | "password";

// The API answers in English, with statuses that mean something different
// per route: shown in French here.
const MESSAGES: Record<AuthAction, Record<number, string>> = {
  login: {
    401: "Email ou mot de passe incorrect. Compte 42 sans mot de passe ? Utilisez « Se connecter avec 42 ».",
    403: "Ce compte est suspendu.",
    422: "Email ou mot de passe invalide.",
  },
  register: {
    403: "Cette adresse se connecte avec « Se connecter avec 42 ».",
    409: "Un compte existe déjà avec cet email. Compte 42 ? Connectez-vous avec 42.",
    422: `Vérifiez l'email, le nom et le mot de passe (${MIN_PASSWORD_LENGTH} caractères minimum).`,
  },
  password: {
    400: "Mot de passe actuel incorrect.",
    401: "Session expirée, reconnectez-vous.",
    403: "Pour définir un premier mot de passe, reconnectez-vous d'abord avec 42.",
    422: `Le mot de passe doit contenir entre ${MIN_PASSWORD_LENGTH} et ${MAX_PASSWORD_LENGTH} caractères.`,
  },
};

export function authErrorMessage(action: AuthAction, err: unknown): string {
  if (!(err instanceof ApiError)) return "Serveur injoignable, réessayez.";
  if (err.status === 429) {
    // nginx's per-IP limit says 1 s, the API's per-email limit up to an hour
    const wait = err.retryAfter;
    const when = !wait
      ? "plus tard"
      : wait < 60
        ? "dans quelques secondes"
        : `dans ${Math.ceil(wait / 60)} min`;
    return `Trop de tentatives, réessayez ${when}.`;
  }
  return MESSAGES[action][err.status] ?? "Une erreur est survenue. Réessayez.";
}
