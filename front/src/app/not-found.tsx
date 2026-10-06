import type { Metadata } from 'next';
import { Button } from '@/components/ui/Button';

export const metadata: Metadata = {
  title: 'Page introuvable | LeBon42',
  description: "La page ou l'annonce demandée n'existe pas ou a été déplacée.",
};

export default function NotFound() {
  return (
    <main className="min-h-[70vh] flex items-center justify-center px-4 sm:px-6 lg:px-8 py-16">
      <div className="max-w-md w-full text-center space-y-6 bg-white p-8 sm:p-10 rounded-2xl border border-slate-200/80 shadow-xs">
        {/* Badge 404 stylisé */}
        <div className="w-16 h-16 mx-auto rounded-full bg-[#00babc]/10 border border-[#00babc]/20 flex items-center justify-center text-[#00babc] font-black text-2xl tracking-tight shadow-xs">
          404
        </div>

        {/* Textes explicatifs */}
        <div className="space-y-2">
          <h1 className="text-xl sm:text-2xl font-bold text-slate-900 tracking-tight">
            Page ou annonce introuvable
          </h1>
          <p className="text-sm text-slate-600 leading-relaxed">
            L&apos;annonce ou la page que vous recherchez n&apos;existe pas, a été supprimée ou l&apos;adresse saisie est incorrecte.
          </p>
        </div>

        {/* Actions de navigation */}
        <div className="flex flex-col sm:flex-row items-center justify-center gap-3 pt-2">
          <Button
            href="/"
            variant="primary"
            size="md"
            className="w-full sm:w-auto"
          >
            Retour aux annonces
          </Button>
          <Button
            href="/listings/create"
            variant="outline"
            size="md"
            className="w-full sm:w-auto"
          >
            Déposer une annonce
          </Button>
        </div>
      </div>
    </main>
  );
}
