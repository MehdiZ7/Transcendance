"use client";

import { useEffect, useId, useRef, useState } from "react";
import { Button } from "@/components/ui/Button";
import { useAuthModal } from "@/context/AuthModalContext";
import { authErrorMessage } from "@/lib/api/auth";
import { MIN_PASSWORD_LENGTH, MAX_PASSWORD_LENGTH, MAX_DISPLAY_NAME_LENGTH } from "@/lib/limits";

// Same shape EmailStr accepts (a dot in the domain): an address the API took
// at sign-up always passes, a malformed one never costs an auth request
const EMAIL_RE = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;

type Mode = "login" | "register";

interface FieldErrors {
  displayName?: string;
  email?: string;
  password?: string;
  confirmPassword?: string;
}

// Input id suffixes, in form order: the first invalid one gets the focus
const FIELD_IDS: Record<keyof FieldErrors, string> = {
  displayName: "display-name",
  email: "email",
  password: "password",
  confirmPassword: "confirm-password",
};

const getInputClass = (hasError: boolean) =>
  `w-full px-3.5 py-2.5 rounded-xl text-sm transition-all focus:outline-hidden focus:bg-white ${
    hasError
      ? "bg-rose-50/50 border border-rose-400 text-rose-950 placeholder:text-rose-300 focus:border-rose-500 focus:ring-2 focus:ring-rose-500/20"
      : "bg-slate-50/50 border border-slate-200 text-slate-900 placeholder:text-slate-400 focus:border-[#00babc] focus:ring-2 focus:ring-[#00babc]/20"
  }`;

const getLabelClass = (hasError: boolean) =>
  `block text-xs font-semibold uppercase tracking-wider mb-1.5 transition-colors ${
    hasError ? "text-rose-600 font-bold" : "text-slate-700"
  }`;

function FieldError({ id, message }: { id: string; message?: string }) {
  if (!message) return null;
  return (
    <p id={id} className="mt-1.5 text-xs text-rose-600 font-medium flex items-center gap-1.5">
      <span aria-hidden="true" className="w-1.5 h-1.5 rounded-full bg-rose-500 shrink-0" />
      <span>{message}</span>
    </p>
  );
}

// Login and sign-up tabs plus the 42 button. Used by the auth modal and the
// /login page, where `next` is the protected page the visitor asked for.
export function AuthForm({ next }: { next?: string }) {
  const { loginWith42, loginWithPassword, register, isLoggingIn } = useAuthModal();
  // unique ids: the modal can open on top of the /login page
  const id = useId();

  const [mode, setMode] = useState<Mode>("login");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [displayName, setDisplayName] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [fieldErrors, setFieldErrors] = useState<FieldErrors>({});
  // set by a refused submit, consumed once the errors are rendered
  const focusFirstError = useRef(false);

  const inputId = (field: keyof FieldErrors) => `${id}-${FIELD_IDS[field]}`;
  // noValidate silences the browser's own messages: these props let a screen
  // reader find ours (read out with the label when the input gets the focus)
  const errorProps = (field: keyof FieldErrors) =>
    fieldErrors[field]
      ? { "aria-invalid": true, "aria-describedby": `${inputId(field)}-error` }
      : {};

  // after the render, so aria-describedby already points at the message
  useEffect(() => {
    if (!focusFirstError.current) return;
    focusFirstError.current = false;
    const first = (Object.keys(FIELD_IDS) as (keyof FieldErrors)[]).find((f) => fieldErrors[f]);
    if (first) document.getElementById(inputId(first))?.focus();
  });

  const switchMode = (m: Mode) => {
    setMode(m);
    setError(null);
    setFieldErrors({});
  };

  const handleFieldChange = (
    field: keyof FieldErrors,
    value: string,
    setter: (val: string) => void
  ) => {
    setter(value);
    if (fieldErrors[field]) {
      setFieldErrors((prev) => {
        const copy = { ...prev };
        delete copy[field];
        return copy;
      });
    }
    if (error) {
      setError(null);
    }
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    const errors: FieldErrors = {};

    // no upper bounds here: each input's maxLength already caps its length
    if (mode === "register" && !displayName.trim()) {
      errors.displayName = "Le nom affiché est requis.";
    }
    if (!email.trim()) {
      errors.email = "L'adresse email est requise.";
    } else if (!EMAIL_RE.test(email.trim())) {
      errors.email = "Format d'adresse email invalide.";
    }
    if (!password) {
      errors.password = "Le mot de passe est requis.";
    }
    if (mode === "register") {
      // Creation rules only: an existing password is never re-checked
      // against them at login
      if (password && password.length < MIN_PASSWORD_LENGTH) {
        errors.password = `Le mot de passe doit contenir au moins ${MIN_PASSWORD_LENGTH} caractères.`;
      }
      if (!confirmPassword) {
        errors.confirmPassword = "La confirmation du mot de passe est requise.";
      } else if (password !== confirmPassword) {
        errors.confirmPassword = "Les mots de passe ne correspondent pas.";
      }
    }

    setFieldErrors(errors);
    if (Object.keys(errors).length > 0) {
      focusFirstError.current = true;
      return;
    }

    try {
      if (mode === "register") {
        await register({ email: email.trim(), password, display_name: displayName.trim() }, next);
      } else {
        await loginWithPassword(email.trim(), password, next);
      }
    } catch (err) {
      setError(authErrorMessage(mode, err));
    }
  };

  return (
    <div className="space-y-5">
      {/* Login / sign-up tabs */}
      <div className="grid grid-cols-2 gap-1 p-1 rounded-xl bg-slate-100">
        {(["login", "register"] as const).map((m) => (
          <button
            key={m}
            type="button"
            onClick={() => switchMode(m)}
            className={`py-2 rounded-lg text-sm font-semibold transition-colors cursor-pointer ${
              mode === m ? "bg-white text-slate-900 shadow-xs" : "text-slate-500 hover:text-slate-800"
            }`}
          >
            {m === "login" ? "Connexion" : "Inscription"}
          </button>
        ))}
      </div>

      <form onSubmit={handleSubmit} noValidate className="space-y-3.5 text-left">
        {mode === "register" && (
          <div>
            <label htmlFor={inputId("displayName")} className={getLabelClass(Boolean(fieldErrors.displayName))}>
              Nom affiché
            </label>
            <input
              id={inputId("displayName")}
              type="text"
              required
              maxLength={MAX_DISPLAY_NAME_LENGTH}
              autoComplete="nickname"
              value={displayName}
              onChange={(e) => handleFieldChange("displayName", e.target.value, setDisplayName)}
              className={getInputClass(Boolean(fieldErrors.displayName))}
              {...errorProps("displayName")}
            />
            <FieldError id={`${inputId("displayName")}-error`} message={fieldErrors.displayName} />
          </div>
        )}

        <div>
          <label htmlFor={inputId("email")} className={getLabelClass(Boolean(fieldErrors.email))}>
            Email
          </label>
          <input
            id={inputId("email")}
            type="email"
            required
            autoComplete="email"
            value={email}
            onChange={(e) => handleFieldChange("email", e.target.value, setEmail)}
            className={getInputClass(Boolean(fieldErrors.email))}
            {...errorProps("email")}
          />
          <FieldError id={`${inputId("email")}-error`} message={fieldErrors.email} />
        </div>

        <div>
          <label htmlFor={inputId("password")} className={getLabelClass(Boolean(fieldErrors.password))}>
            Mot de passe
          </label>
          <input
            id={inputId("password")}
            type="password"
            required
            minLength={mode === "register" ? MIN_PASSWORD_LENGTH : undefined}
            maxLength={MAX_PASSWORD_LENGTH}
            autoComplete={mode === "register" ? "new-password" : "current-password"}
            value={password}
            onChange={(e) => handleFieldChange("password", e.target.value, setPassword)}
            className={getInputClass(Boolean(fieldErrors.password))}
            {...errorProps("password")}
          />
          <FieldError id={`${inputId("password")}-error`} message={fieldErrors.password} />
        </div>

        {mode === "register" && (
          <div>
            <label htmlFor={inputId("confirmPassword")} className={getLabelClass(Boolean(fieldErrors.confirmPassword))}>
              Confirmer le mot de passe
            </label>
            <input
              id={inputId("confirmPassword")}
              type="password"
              required
              minLength={MIN_PASSWORD_LENGTH}
              maxLength={MAX_PASSWORD_LENGTH}
              autoComplete="new-password"
              value={confirmPassword}
              onChange={(e) => handleFieldChange("confirmPassword", e.target.value, setConfirmPassword)}
              className={getInputClass(Boolean(fieldErrors.confirmPassword))}
              {...errorProps("confirmPassword")}
            />
            <FieldError id={`${inputId("confirmPassword")}-error`} message={fieldErrors.confirmPassword} />
          </div>
        )}

        {error && (
          <p
            role="alert"
            className="text-sm text-rose-600 bg-rose-50 border border-rose-200 rounded-lg px-3 py-2"
          >
            {error}
          </p>
        )}

        <Button
          type="submit"
          variant="primary"
          size="md"
          fullWidth
          isLoading={isLoggingIn}
          disabled={isLoggingIn}
          className="font-bold"
        >
          {mode === "register" ? "Créer mon compte" : "Se connecter"}
        </Button>
      </form>

      {/* Divider */}
      <div className="flex items-center gap-3">
        <span className="flex-1 h-px bg-slate-200" />
        <span className="text-xs text-slate-400">ou</span>
        <span className="flex-1 h-px bg-slate-200" />
      </div>

      {/* 42 login. An arrow, not onClick={loginWith42}: the click event would arrive as `next` */}
      <Button
        type="button"
        variant="outline"
        size="md"
        fullWidth
        onClick={() => loginWith42(next)}
        disabled={isLoggingIn}
        className="font-bold"
      >
        <span className="inline-flex items-center gap-2">
          <span className="text-[#00babc] font-black">42</span>
          <span>Se connecter avec 42</span>
        </span>
      </Button>

      {isLoggingIn && (
        <p className="text-xs text-slate-500 text-center">Connexion en cours…</p>
      )}
    </div>
  );
}
