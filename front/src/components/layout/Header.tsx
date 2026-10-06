"use client";

import { useState, useEffect } from 'react';
import Link from 'next/link';
import { usePathname } from 'next/navigation';
import { Button } from '@/components/ui/Button';
import { Modal } from '@/components/ui/Modal';
import { UserRole } from '@/types/user';
import { useCurrentUser } from '@/hooks/useCurrentUser';
import { useAuthModal } from '@/context/AuthModalContext';

interface NavItem {
  label: string;
  href: string;
  icon: React.ReactNode;
  roles?: UserRole[];
}

const NAV_ITEMS: NavItem[] = [
  {
    label: 'Annonces',
    href: '/',
    icon: (
      <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
        <path strokeLinecap="round" strokeLinejoin="round" d="M16 11V7a4 4 0 00-8 0v4M5 9h14l1 12H4L5 9z" />
      </svg>
    ),
  },
  {
    label: 'Profil',
    href: '/profile',
    icon: (
      <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
        <path strokeLinecap="round" strokeLinejoin="round" d="M16 7a4 4 0 11-8 0 4 4 0 018 0zM12 14a7 7 0 00-7 7h14a7 7 0 00-7-7z" />
      </svg>
    ),
  },
  {
    label: 'Messages',
    href: '/messages',
    icon: (
      <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
        <path
          strokeLinecap="round"
          strokeLinejoin="round"
          d="M8 12h.01M12 12h.01M16 12h.01M21 12c0 4.418-4.03 8-9 8a9.863 9.863 0 01-4.255-.949L3 20l1.395-3.72C3.512 15.042 3 13.574 3 12c0-4.418 4.03-8 9-8s9 3.582 9 8z"
        />
      </svg>
    ),
  },
  {
    label: 'Moderation',
    href: '/moderation',
    roles: ['moderator', 'admin'],
    icon: (
      <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
        <path
          strokeLinecap="round"
          strokeLinejoin="round"
          d="M9 12l2 2 4-4m5.618-4.016A11.955 11.955 0 0112 2.944a11.955 11.955 0 01-8.618 3.04A12.02 12.02 0 003 9c0 5.591 3.824 10.29 9 11.622 5.176-1.332 9-6.03 9-11.622 0-1.042-.133-2.052-.382-3.016z"
        />
      </svg>
    ),
  },
  {
    label: 'Analytics',
    href: '/analytics',
    roles: ['admin'],
    icon: (
      <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
        <path
          strokeLinecap="round"
          strokeLinejoin="round"
          d="M9 19v-6a2 2 0 00-2-2H5a2 2 0 00-2 2v6a2 2 0 002 2h2a2 2 0 002-2zm0 0V9a2 2 0 012-2h2a2 2 0 012 2v10m-6 0a2 2 0 002 2h2a2 2 0 002-2m0 0V5a2 2 0 012-2h2a2 2 0 012 2v14a2 2 0 01-2 2h-2a2 2 0 01-2-2z"
        />
      </svg>
    ),
  },
];

export default function Header() {
  const [isMobileMenuOpen, setIsMobileMenuOpen] = useState(false);
  const [isLogoutModalOpen, setIsLogoutModalOpen] = useState(false);
  const pathname = usePathname();

  //check if the item role is similar (or public) as the user role
  const { user, role, logout } = useCurrentUser();
  const { openAuthModal, isLoggingIn } = useAuthModal();

  const visibleItems = NAV_ITEMS.filter(
    (item) => !item.roles || (role !== null && item.roles.includes(role))
  );

  // Close mobile menu on route change
  const [prevPathname, setPrevPathname] = useState(pathname);
  if (prevPathname !== pathname) {
    setPrevPathname(pathname);
    setIsMobileMenuOpen(false);
  }

  // Close on Escape key press
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        setIsMobileMenuOpen(false);
      }
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, []);

  const isActive = (href: string) => {
    if (href === '/') return pathname === '/';
    return pathname.startsWith(href);
  };

  const handleProtectedNavigation = (e: React.MouseEvent, href: string) => {
    if (!user && (href === '/profile' || href === '/messages' || href === '/listings/create')) {
      e.preventDefault();
      setIsMobileMenuOpen(false);
      openAuthModal();
    }
  };

  return (
    <header className="fixed top-0 left-0 right-0 z-50 bg-slate-925/90 backdrop-blur-md border-b border-white/10 text-white transition-all">
      <nav className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 h-16 flex items-center justify-between">
        {/* Logo */}
        <Link
          href="/"
          className="flex items-center gap-1.5 text-xl font-bold tracking-tight text-white group"
          onClick={() => setIsMobileMenuOpen(false)}
        >
          <span className="font-extrabold tracking-normal">LeBon</span>
          <span className="px-1.5 py-0.5 rounded-md bg-[#00babc] text-slate-950 text-xs font-black tracking-wider uppercase shadow-xs group-hover:bg-[#26e5e8] transition-colors">
            42
          </span>
        </Link>

        {/* Desktop central navigation & links */}
        <div className="flex items-center gap-4 sm:gap-6">
          <ul className="hidden sm:flex items-center space-x-6 text-sm font-medium">
            {visibleItems.map((item) => {
              const active = isActive(item.href);
              return (
                <li key={item.href}>
                  <Link
                    href={item.href}
                    onClick={(e) => handleProtectedNavigation(e, item.href)}
                    className={`transition-colors relative py-1 ${active
                        ? 'text-[#00babc] font-semibold'
                        : 'text-gray-300 hover:text-[#00babc]'
                      }`}
                  >
                    {item.label}
                    {active && (
                      <span className="absolute -bottom-1 left-0 right-0 h-0.5 bg-[#00babc] rounded-full" />
                    )}
                  </Link>
                </li>
              );
            })}
          </ul>

          {/* Sell action button */}
          <Button
            href="/listings/create"
            variant="primary"
            size="sm"
            className="shrink-0"
            aria-label="Créer une annonce"
            onClick={(e) => handleProtectedNavigation(e, '/listings/create')}
          >
            <svg
              className="w-4 h-4 stroke-slate-950"
              fill="none"
              viewBox="0 0 24 24"
              strokeWidth={2.5}
            >
              <path strokeLinecap="round" strokeLinejoin="round" d="M12 4.5v15m7.5-7.5h-15" />
            </svg>
            <span className="hidden sm:inline">Créer une annonce</span>
          </Button>

          {/* Auth indicator & actions (Desktop) */}
          <div className="hidden sm:flex items-center gap-3 pl-5 border-l border-white/10">
            {!user ? (
              <Button
                type="button"
                variant="outline"
                size="sm"
                onClick={openAuthModal}
                isLoading={isLoggingIn}
                disabled={isLoggingIn}
                className="text-white border-white/20 hover:bg-white/10 hover:text-[#00babc]"
              >
                {isLoggingIn ? "Connexion..." : "Connexion"}
              </Button>
            ) : (
              <Button
                type="button"
                variant="outline"
                size="sm"
                onClick={() => setIsLogoutModalOpen(true)}
                title="Se déconnecter"
                className="text-white border-white/20 hover:bg-white/10 hover:text-[#00babc]"
              >
                Déconnexion
              </Button>
            )}
          </div>

          {/* Mobile hamburger menu toggle button */}
          <button
            type="button"
            onClick={() => setIsMobileMenuOpen((prev) => !prev)}
            aria-label={isMobileMenuOpen ? 'Fermer le menu' : 'Ouvrir le menu'}
            aria-expanded={isMobileMenuOpen}
            className="sm:hidden p-2 -mr-1 rounded-xl text-gray-300 hover:text-white hover:bg-white/10 transition-colors focus:outline-hidden cursor-pointer"
          >
            {isMobileMenuOpen ? (
              <svg className="w-6 h-6" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                <path strokeLinecap="round" strokeLinejoin="round" d="M6 18L18 6M6 6l12 12" />
              </svg>
            ) : (
              <svg className="w-6 h-6" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                <path strokeLinecap="round" strokeLinejoin="round" d="M4 6h16M4 12h16M4 18h16" />
              </svg>
            )}
          </button>
        </div>
      </nav>

      {/* Mobile navigation drawer / dropdown */}
      {isMobileMenuOpen && (
        <>
          {/* Backdrop overlay */}
          <div
            className="fixed inset-0 top-16 bg-black/60 backdrop-blur-xs z-40 sm:hidden animate-fade-in"
            onClick={() => setIsMobileMenuOpen(false)}
            aria-hidden="true"
          />

          {/* Mobile menu panel */}
          <div className="fixed top-16 left-0 right-0 z-50 bg-slate-925/95 backdrop-blur-xl border-b border-white/10 shadow-2xl p-4 sm:hidden space-y-3">
            <ul className="space-y-1">
              {visibleItems.map((item) => {
                const active = isActive(item.href);
                return (
                  <li key={item.href}>
                    <Link
                      href={item.href}
                      onClick={(e) => handleProtectedNavigation(e, item.href)}
                      className={`flex items-center gap-3 px-4 py-3 rounded-xl text-sm font-medium transition-all ${active
                          ? 'bg-[#00babc]/15 text-[#00babc] font-semibold border border-[#00babc]/30 shadow-xs'
                          : 'text-gray-300 hover:text-white hover:bg-white/5'
                        }`}
                    >
                      <span className={active ? 'text-[#00babc]' : 'text-gray-400'}>
                        {item.icon}
                      </span>
                      <span className="flex-1">{item.label}</span>
                      {active && (
                        <span className="w-1.5 h-1.5 rounded-full bg-[#00babc]" />
                      )}
                    </Link>
                  </li>
                );
              })}
            </ul>

            {/* Quick action in mobile menu */}
            <div className="pt-2 border-t border-white/10 space-y-2">
              <Button
                href="/listings/create"
                variant="primary"
                size="md"
                fullWidth
                onClick={(e) => handleProtectedNavigation(e, '/listings/create')}
              >
                <svg
                  className="w-4 h-4 stroke-slate-950"
                  fill="none"
                  viewBox="0 0 24 24"
                  strokeWidth={2.5}
                >
                  <path strokeLinecap="round" strokeLinejoin="round" d="M12 4.5v15m7.5-7.5h-15" />
                </svg>
                <span>Créer une annonce</span>
              </Button>

              {!user ? (
                <Button
                  type="button"
                  variant="outline"
                  size="md"
                  fullWidth
                  onClick={() => {
                    setIsMobileMenuOpen(false);
                    openAuthModal();
                  }}
                  isLoading={isLoggingIn}
                  disabled={isLoggingIn}
                  className="text-white border-white/20 hover:bg-white/10"
                >
                  {isLoggingIn ? "Connexion..." : "Connexion"}
                </Button>
              ) : (
                <div className="flex items-center justify-between px-3 py-2 rounded-xl bg-white/5 border border-white/10 text-sm">
                  <span className="text-slate-300 truncate">{user.display_name}</span>
                  <Button
                    type="button"
                    variant="ghost"
                    size="sm"
                    onClick={() => {
                      setIsMobileMenuOpen(false);
                      setIsLogoutModalOpen(true);
                    }}
                    className="text-rose-400 hover:text-rose-300 hover:bg-rose-500/10 text-xs"
                  >
                    Déconnexion
                  </Button>
                </div>
              )}
            </div>
          </div>
        </>
      )}

      {/* Confirmation modal on logout */}
      <Modal
        isOpen={isLogoutModalOpen}
        onClose={() => setIsLogoutModalOpen(false)}
        title="Confirmer la déconnexion"
      >
        <div className="space-y-4 pt-1">
          <p className="text-sm text-slate-600 leading-relaxed">
            Êtes-vous sûr de vouloir vous déconnecter de votre compte ?
          </p>
          <div className="flex flex-col-reverse sm:flex-row items-center justify-end gap-2.5 pt-4 border-t border-slate-100">
            <Button
              type="button"
              variant="outline"
              size="sm"
              onClick={() => setIsLogoutModalOpen(false)}
              className="w-full sm:w-auto"
            >
              Annuler
            </Button>
            <Button
              type="button"
              variant="danger"
              size="sm"
              onClick={async () => {
                setIsLogoutModalOpen(false);
                await logout();
              }}
              className="w-full sm:w-auto"
            >
              Oui, me déconnecter
            </Button>
          </div>
        </div>
      </Modal>
    </header>
  );
}
