"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";
import { useCurrentUser } from "@/hooks/useCurrentUser";
import { useAuthModal } from "@/context/AuthModalContext";

export function AuthGuard({ children }: { children: React.ReactNode }) {
  const router = useRouter();
  const { user, isLoading } = useCurrentUser();
  const { openAuthModal } = useAuthModal();

  useEffect(() => {
    if (!isLoading && !user) {
      openAuthModal();
      router.replace("/");
    }
  }, [isLoading, user, openAuthModal, router]);

  if (isLoading) {
    return (
      <main className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-12 text-sm text-gray-500">
        Chargement…
      </main>
    );
  }

  if (!user) {
    return null;
  }

  return <>{children}</>;
}
