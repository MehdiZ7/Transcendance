"use client";

import React, { createContext, useContext, useState, useCallback } from "react";
import { authApi } from "@/lib/api/auth";
import type { RegisterInput } from "@/types/auth";

interface AuthModalContextType {
  isAuthModalOpen: boolean;
  isLoggingIn: boolean;
  openAuthModal: () => void;
  closeAuthModal: () => void;
  // `next`: a path on this site to land on once logged in, default the current page
  loginWith42: (next?: string) => void;
  loginWithPassword: (email: string, password: string, next?: string) => Promise<void>;
  register: (input: RegisterInput, next?: string) => Promise<void>;
}

// A path on this site, never another host: same rule as _safe_next in
// backend/src/app/api/auth.py ("//host", "/\\host"… resolve to another origin).
function safeNext(next: string | undefined): string | null {
  if (!next) return null;
  try {
    const url = new URL(next, window.location.origin);
    if (url.origin !== window.location.origin || url.pathname.startsWith("/api/")) return null;
    return url.pathname + url.search + url.hash;
  } catch {
    return null;
  }
}

// Where to go once logged in: no `next` is the current page; a `next` that is
// not a path on this site is the home page (never back to /login itself)
function afterLogin(next: string | undefined): string {
  if (next === undefined) return window.location.pathname + window.location.search;
  return safeNext(next) ?? "/";
}

const AuthModalContext = createContext<AuthModalContextType | undefined>(undefined);

export function AuthModalProvider({ children }: { children: React.ReactNode }) {
  const [isAuthModalOpen, setIsAuthModalOpen] = useState(false);
  const [isLoggingIn, setIsLoggingIn] = useState(false);

  const openAuthModal = useCallback(() => {
    setIsAuthModalOpen(true);
  }, []);

  const closeAuthModal = useCallback(() => {
    if (isLoggingIn) return; // do not close while a redirect is already in flight
    setIsAuthModalOpen(false);
  }, [isLoggingIn]);

  const loginWith42 = useCallback((next?: string) => {
    setIsLoggingIn(true);
    // the backend checks `next` again and brings the browser back to it
    const target = afterLogin(next);
    // Tiny delay so React can paint the loading state first
    setTimeout(() => {
      // eslint-disable-next-line @next/next/no-location-assign-relative-destination -- full navigation to the OAuth API route, not a Next.js page
      window.location.href = `/api/auth/login?next=${encodeURIComponent(target)}`;
    }, 50);
  }, []);

  const loginWithPassword = useCallback(async (email: string, password: string, next?: string) => {
    setIsLoggingIn(true);
    try {
      await authApi.login({ email, password });
      // a full navigation, not router.push: it resets the user cache of useCurrentUser
      window.location.assign(afterLogin(next));
    } catch (err) {
      setIsLoggingIn(false);
      throw err;
    }
  }, []);

  const register = useCallback(async (input: RegisterInput, next?: string) => {
    setIsLoggingIn(true);
    try {
      await authApi.register(input);
      window.location.assign(afterLogin(next));
    } catch (err) {
      setIsLoggingIn(false);
      throw err;
    }
  }, []);

  return (
    <AuthModalContext.Provider
      value={{
        isAuthModalOpen,
        isLoggingIn,
        openAuthModal,
        closeAuthModal,
        loginWith42,
        loginWithPassword,
        register,
      }}
    >
      {children}
    </AuthModalContext.Provider>
  );
}

export function useAuthModal() {
  const context = useContext(AuthModalContext);
  if (!context) {
    throw new Error("useAuthModal must be used within an AuthModalProvider");
  }
  return context;
}
