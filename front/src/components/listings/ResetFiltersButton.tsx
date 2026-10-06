'use client';

import React, { useState } from 'react';
import { useRouter } from 'next/navigation';
import { Button } from '@/components/ui/Button';
import { Modal } from '@/components/ui/Modal';

interface ResetFiltersButtonProps {
  className?: string;
  children?: React.ReactNode;
}

export function ResetFiltersButton({
  className = '',
  children = 'Réinitialiser les filtres',
}: ResetFiltersButtonProps) {
  const router = useRouter();
  const [isOpen, setIsOpen] = useState(false);

  const handleConfirm = () => {
    setIsOpen(false);
    router.push('/');
  };

  return (
    <>
      <button
        type="button"
        onClick={() => setIsOpen(true)}
        className={`cursor-pointer ${className}`}
      >
        {children}
      </button>

      <Modal
        isOpen={isOpen}
        onClose={() => setIsOpen(false)}
        title="Réinitialiser les filtres ?"
      >
        <div className="space-y-4 pt-1">
          <p className="text-sm text-slate-600 leading-relaxed">
            Êtes-vous sûr de vouloir réinitialiser tous les filtres de recherche (recherche textuelle, campus, catégorie, tri et prix) ?
          </p>
          <div className="flex flex-col-reverse sm:flex-row items-center justify-end gap-2.5 pt-4 border-t border-slate-100">
            <Button
              type="button"
              variant="outline"
              size="sm"
              onClick={() => setIsOpen(false)}
              className="w-full sm:w-auto bg-white"
            >
              Annuler
            </Button>
            <Button
              type="button"
              variant="danger"
              size="sm"
              onClick={handleConfirm}
              className="w-full sm:w-auto"
            >
              Oui, réinitialiser
            </Button>
          </div>
        </div>
      </Modal>
    </>
  );
}

export default ResetFiltersButton;
