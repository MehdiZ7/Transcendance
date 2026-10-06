"use client";

import { useState } from "react";
import { Button } from "@/components/ui/Button";
import { useAuthModal } from "@/context/AuthModalContext";
import { ApiError } from "@/lib/api/client";
import { authApi, authErrorMessage } from "@/lib/api/auth";
import { MIN_PASSWORD_LENGTH, MAX_PASSWORD_LENGTH } from "@/lib/limits";

const inputClass =
  "w-full px-3.5 py-2.5 rounded-xl bg-slate-50/50 border border-slate-200 text-slate-900 text-sm placeholder:text-slate-400 focus:outline-hidden focus:bg-white focus:border-[#00babc] focus:ring-2 focus:ring-[#00babc]/20 transition-all";

export function PasswordForm({ hasPassword: initialHasPassword }: { hasPassword: boolean }) {
  const { loginWith42, isLoggingIn } = useAuthModal();
  // flips once a first password is set: the next change must prove it
  const [hasPassword, setHasPassword] = useState(initialHasPassword);
  // a 42 account's session is too old to set a first password (403)
  const [needsFresh42Login, setNeedsFresh42Login] = useState(false);
  const [currentPassword, setCurrentPassword] = useState("");
  const [newPassword, setNewPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [isSaving, setIsSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [isSuccess, setIsSuccess] = useState(false);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    setIsSuccess(false);
    setNeedsFresh42Login(false);

    if (newPassword.length < MIN_PASSWORD_LENGTH) {
      setError(`Le mot de passe doit contenir au moins ${MIN_PASSWORD_LENGTH} caractères.`);
      return;
    }
    if (newPassword !== confirmPassword) {
      setError("Les mots de passe ne correspondent pas.");
      return;
    }
    if (hasPassword && !currentPassword) {
      setError("Le mot de passe actuel est requis.");
      return;
    }

    setIsSaving(true);
    try {
      await authApi.changePassword({
        new_password: newPassword,
        ...(hasPassword ? { current_password: currentPassword } : {}),
      });
      setIsSuccess(true);
      setHasPassword(true);
      setCurrentPassword("");
      setNewPassword("");
      setConfirmPassword("");
    } catch (err) {
      setError(authErrorMessage("password", err));
      setNeedsFresh42Login(!hasPassword && err instanceof ApiError && err.status === 403);
    } finally {
      setIsSaving(false);
    }
  };

  return (
    <section className="space-y-4 mt-6 pt-6 border-t border-gray-100">
      <div>
        <h3 className="text-sm font-bold text-slate-900 uppercase tracking-wider">
          {hasPassword ? "Changer le mot de passe" : "Définir un mot de passe"}
        </h3>
        <p className="text-xs text-slate-500 mt-1">
          {hasPassword
            ? "Mettez à jour le mot de passe de votre compte."
            : "Vous vous connectez avec 42 : vous pouvez aussi définir un mot de passe, dans les 10 minutes qui suivent une connexion avec 42."}
        </p>
      </div>

      <form onSubmit={handleSubmit} className="space-y-3">
        {hasPassword && (
          <input
            type="password"
            required
            maxLength={MAX_PASSWORD_LENGTH}
            autoComplete="current-password"
            placeholder="Mot de passe actuel"
            aria-label="Mot de passe actuel"
            value={currentPassword}
            onChange={(e) => setCurrentPassword(e.target.value)}
            className={inputClass}
          />
        )}

        <input
          type="password"
          required
          minLength={MIN_PASSWORD_LENGTH}
          maxLength={MAX_PASSWORD_LENGTH}
          autoComplete="new-password"
          placeholder="Nouveau mot de passe"
          aria-label="Nouveau mot de passe"
          value={newPassword}
          onChange={(e) => setNewPassword(e.target.value)}
          className={inputClass}
        />

        <input
          type="password"
          required
          minLength={MIN_PASSWORD_LENGTH}
          maxLength={MAX_PASSWORD_LENGTH}
          autoComplete="new-password"
          placeholder="Confirmer le nouveau mot de passe"
          aria-label="Confirmer le nouveau mot de passe"
          value={confirmPassword}
          onChange={(e) => setConfirmPassword(e.target.value)}
          className={inputClass}
        />

        {error && (
          <p role="alert" className="text-sm text-rose-600">
            {error}
          </p>
        )}
        {needsFresh42Login && (
          <Button
            type="button"
            variant="outline"
            size="md"
            onClick={() => loginWith42("/profile")}
            isLoading={isLoggingIn}
            disabled={isLoggingIn}
          >
            Se reconnecter avec 42
          </Button>
        )}
        {isSuccess && <p className="text-sm text-emerald-600">Mot de passe mis à jour.</p>}

        <Button type="submit" variant="primary" size="md" isLoading={isSaving} disabled={isSaving}>
          Enregistrer le mot de passe
        </Button>
      </form>
    </section>
  );
}
