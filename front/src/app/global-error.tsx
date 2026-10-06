'use client';

import { useEffect } from 'react';
import '@/app/globals.css';
import { logError } from '@/lib/log';

interface GlobalErrorProps {
  error: Error & { digest?: string };
  reset: () => void;
}

export default function GlobalError({ error, reset }: GlobalErrorProps) {
  useEffect(() => {
    logError('Unhandled global error:', error);
  }, [error]);

  return (
    <html lang="fr">
      <body className="bg-gray-50 text-gray-900 min-h-screen flex items-center justify-center p-4">
        <div className="max-w-md w-full text-center space-y-6 bg-white p-8 rounded-2xl border border-slate-200/80 shadow-xs">
          <div className="w-14 h-14 mx-auto rounded-full bg-rose-50 border border-rose-100 flex items-center justify-center text-rose-500 text-2xl font-bold">
            ⚠️
          </div>

          <div className="space-y-2">
            <h1 className="text-xl font-bold text-slate-900">
              Erreur critique
            </h1>
            <p className="text-sm text-slate-600">
              Une erreur système majeure est survenue. Veuillez rafraîchir l&apos;application.
            </p>
            {error.digest && (
              <p className="text-xs text-slate-400 font-mono">
                Code : {error.digest}
              </p>
            )}
          </div>

          <div className="pt-2">
            <button
              type="button"
              onClick={reset}
              className="px-6 py-2.5 rounded-xl bg-[#00babc] hover:bg-[#26e5e8] text-slate-950 font-bold text-sm shadow-xs transition-all cursor-pointer"
            >
              Recharger l&apos;application
            </button>
          </div>
        </div>
      </body>
    </html>
  );
}
