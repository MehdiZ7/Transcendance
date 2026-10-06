'use client';

import { useEffect } from 'react';
import { Button } from '@/components/ui/Button';
import { logError } from '@/lib/log';

interface ErrorProps {
  error: Error & { digest?: string };
  reset: () => void;
}

export default function ErrorBoundary({ error, reset }: ErrorProps) {
  useEffect(() => {
    logError('Unhandled application error:', error);
  }, [error]);

  return (
    <main className="min-h-[70vh] flex items-center justify-center px-4 sm:px-6 lg:px-8 py-16">
      <div className="max-w-md w-full text-center space-y-6 bg-white p-8 rounded-2xl border border-slate-200/80 shadow-xs">
        <div className="w-14 h-14 mx-auto rounded-full bg-rose-50 border border-rose-100 flex items-center justify-center text-rose-500">
          <svg className="w-7 h-7" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
            <path
              strokeLinecap="round"
              strokeLinejoin="round"
              d="M12 9v3.75m-9.303 3.376c-.866 1.5.217 3.374 1.948 3.374h14.71c1.73 0 2.813-1.874 1.948-3.374L13.949 3.378c-.866-1.5-3.032-1.5-3.898 0L2.697 16.126zM12 15.75h.007v.008H12v-.008z"
            />
          </svg>
        </div>

        <div className="space-y-2">
          <h1 className="text-xl sm:text-2xl font-bold text-slate-900">
            Une erreur inattendue est survenue
          </h1>
          <p className="text-sm text-slate-600 leading-relaxed">
            {error.message || "L'opération n'a pas pu aboutir. Veuillez réessayer ou revenir à l'accueil."}
          </p>
          {error.digest && (
            <p className="text-xs text-slate-400 font-mono mt-1">
              Code : {error.digest}
            </p>
          )}
        </div>

        <div className="flex flex-col sm:flex-row items-center justify-center gap-3 pt-2">
          <Button
            type="button"
            variant="outline"
            size="md"
            onClick={reset}
            className="w-full sm:w-auto"
          >
            Réessayer
          </Button>
          <Button
            href="/"
            variant="primary"
            size="md"
            className="w-full sm:w-auto"
          >
            Retour à l&apos;accueil
          </Button>
        </div>
      </div>
    </main>
  );
}
