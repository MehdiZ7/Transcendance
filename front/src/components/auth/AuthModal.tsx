"use client";

import { Modal } from "@/components/ui/Modal";
import { AuthForm } from "@/components/auth/AuthForm";
import { useAuthModal } from "@/context/AuthModalContext";

export function AuthModal() {
  const { isAuthModalOpen, closeAuthModal, isLoggingIn } = useAuthModal();

  return (
    <>
      {/* Global loading bar at the top of the screen during login */}
      {isLoggingIn && (
        <div className="fixed top-0 left-0 right-0 z-[120] h-1 bg-[#00babc]/20 overflow-hidden">
          <div className="h-full bg-gradient-to-r from-[#00babc] via-[#26e5e8] to-[#00babc] w-full animate-pulse shadow-[0_0_12px_rgba(0,186,188,0.8)]" />
        </div>
      )}

      {/* Closing unmounts the form, which resets it. closeAuthModal refuses while
          a login is in flight. */}
      <Modal isOpen={isAuthModalOpen} onClose={closeAuthModal} title="Connexion">
        <div className="pt-1 pb-1">
          <AuthForm />
        </div>
      </Modal>
    </>
  );
}
