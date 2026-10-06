import Link from 'next/link';

export default function Footer() {
  const currentYear = new Date().getFullYear();

  return (
    <footer className="border-t border-gray-200 bg-white text-gray-600 mt-auto">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8 sm:py-10">
        <div className="flex flex-col md:flex-row items-center justify-between gap-6">
          {/* Logo & description */}
          <div className="flex flex-col sm:flex-row items-center gap-3 text-center sm:text-left">
            <Link
              href="/"
              className="flex items-center gap-1.5 text-lg font-bold text-gray-900 group"
            >
              <span>LeBon</span>
              <span className="px-1.5 py-0.5 rounded-md bg-[#00babc] text-slate-950 text-xs font-black tracking-wider uppercase">
                42
              </span>
            </Link>
            <span className="hidden sm:inline text-gray-300">|</span>
            <p className="text-xs sm:text-sm text-gray-500">
              La marketplace étudiante de l&apos;école 42
            </p>
          </div>
        </div>

        {/* Bottom copyright bar */}
        <div className="mt-8 pt-6 border-t border-gray-100 flex flex-col sm:flex-row items-center justify-between gap-3 text-xs text-gray-400 text-center sm:text-left">
          <p>© {currentYear} LeBon42. Tous droits réservés.</p>
          <nav className="flex flex-wrap items-center justify-center gap-x-4 gap-y-1">
            <Link
              href="/browsers"
              className="transition-colors hover:text-gray-600 hover:underline underline-offset-2"
            >
              Navigateurs pris en charge
            </Link>
            <Link
              href="/privacy"
              className="transition-colors hover:text-gray-600 hover:underline underline-offset-2"
            >
              Politique de confidentialité
            </Link>
            <Link
              href="/terms"
              className="transition-colors hover:text-gray-600 hover:underline underline-offset-2"
            >
              Conditions d’utilisation
            </Link>
          </nav>
          <p className="flex items-center gap-1">
            Fait par et pour les étudiants du campus 42
          </p>
        </div>
      </div>
    </footer>
  );
}
