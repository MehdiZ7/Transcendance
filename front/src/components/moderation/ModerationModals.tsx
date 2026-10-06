import { Modal } from '@/components/ui/Modal';
import { Button } from '@/components/ui/Button';
import { getTargetUser } from './types';
import type { Report } from '@/types/report';

interface ModerationModalsProps {
  reportToDelete: Report | null;
  reportToBlock: Report | null;
  reportToReopen: Report | null;
  reportToReject: Report | null;
  onCloseDelete: () => void;
  onConfirmDelete: () => void;
  onCloseBlock: () => void;
  onConfirmBlock: () => void;
  onCloseReopen: () => void;
  onConfirmReopen: () => void;
  onCloseReject: () => void;
  onConfirmReject: () => void;
}

export function ModerationModals({
  reportToDelete,
  reportToBlock,
  reportToReopen,
  reportToReject,
  onCloseDelete,
  onConfirmDelete,
  onCloseBlock,
  onConfirmBlock,
  onCloseReopen,
  onConfirmReopen,
  onCloseReject,
  onConfirmReject,
}: ModerationModalsProps) {
  return (
    <>
      {/* Confirmation modal on delete / suspend */}
      <Modal
        isOpen={Boolean(reportToDelete)}
        onClose={onCloseDelete}
        title={
          reportToDelete?.target_type === 'listing'
            ? "Supprimer l'annonce ?"
            : reportToDelete?.target_type === 'message'
            ? 'Supprimer le message ?'
            : reportToDelete?.target_type === 'user'
            ? "Suspendre l'utilisateur ?"
            : reportToDelete?.target_type === 'review'
            ? "Supprimer l'avis ?"
            : 'Confirmer la suppression ?'
        }
      >
        <div className="space-y-4 pt-1">
          <p className="text-sm text-slate-600 leading-relaxed">
            {reportToDelete?.target_type === 'listing'
              ? "Êtes-vous sûr de vouloir supprimer cette annonce ? Cette action est irréversible, l'annonce sera retirée de la plateforme et le signalement classé comme résolu."
              : reportToDelete?.target_type === 'message'
              ? 'Êtes-vous sûr de vouloir supprimer ce message ? Cette action est irréversible et le signalement sera classé comme résolu.'
              : reportToDelete?.target_type === 'user'
              ? "Êtes-vous sûr de vouloir suspendre ce compte utilisateur ? L'accès sera restreint et le signalement sera classé comme résolu."
              : reportToDelete?.target_type === 'review'
              ? "Êtes-vous sûr de vouloir supprimer cet avis ? Cette action est irréversible, l'avis sera retiré et le signalement classé comme résolu."
              : 'Êtes-vous sûr de vouloir effectuer cette action ? Cette action est irréversible.'}
          </p>

          <div className="flex flex-col-reverse sm:flex-row items-center justify-end gap-2.5 pt-4 border-t border-slate-100">
            <Button
              type="button"
              variant="outline"
              size="sm"
              onClick={onCloseDelete}
              className="w-full sm:w-auto bg-white"
            >
              Annuler
            </Button>
            <Button
              type="button"
              variant="danger"
              size="sm"
              onClick={onConfirmDelete}
              className="w-full sm:w-auto"
            >
              {reportToDelete?.target_type === 'listing'
                ? "Oui, supprimer l'annonce"
                : reportToDelete?.target_type === 'message'
                ? 'Oui, supprimer le message'
                : reportToDelete?.target_type === 'user'
                ? "Oui, suspendre l'utilisateur"
                : reportToDelete?.target_type === 'review'
                ? "Oui, supprimer l'avis"
                : 'Oui, supprimer'}
            </Button>
          </div>
        </div>
      </Modal>

      {/* Confirmation modal on block user */}
      <Modal
        isOpen={Boolean(reportToBlock)}
        onClose={onCloseBlock}
        title="Bloquer l'utilisateur ?"
      >
        <div className="space-y-4 pt-1">
          <p className="text-sm text-slate-600 leading-relaxed">
            Êtes-vous sûr de vouloir bloquer{' '}
            <strong className="text-slate-900 font-semibold">
              {getTargetUser(reportToBlock)?.display_name || 'cet utilisateur'}
            </strong>{' '}
            ? Cet utilisateur ne pourra plus publier d&apos;annonces ni envoyer
            de messages sur la plateforme. Le signalement sera archivé comme
            résolu.
          </p>

          <div className="flex flex-col-reverse sm:flex-row items-center justify-end gap-2.5 pt-4 border-t border-slate-100">
            <Button
              type="button"
              variant="outline"
              size="sm"
              onClick={onCloseBlock}
              className="w-full sm:w-auto bg-white"
            >
              Annuler
            </Button>
            <Button
              type="button"
              variant="danger"
              size="sm"
              onClick={onConfirmBlock}
              className="w-full sm:w-auto"
            >
              Oui, bloquer l&apos;utilisateur
            </Button>
          </div>
        </div>
      </Modal>

      {/* Confirmation modal on reopen / unblock user */}
      <Modal
        isOpen={Boolean(reportToReopen)}
        onClose={onCloseReopen}
        title='Rouvrir le signalement ?'
      >
        <div className="space-y-4 pt-1">
          <p className="text-sm text-slate-600 leading-relaxed">
            
              <>
                Êtes-vous sûr de vouloir rouvrir le signalement{' '}
                <strong className="text-slate-900 font-semibold">
                  #{reportToReopen?.id.slice(-8)}
                </strong>{' '}
                ? Il sera replacé dans la file des signalements à traiter.
              </>
          </p>

          <div className="flex flex-col-reverse sm:flex-row items-center justify-end gap-2.5 pt-4 border-t border-slate-100">
            <Button
              type="button"
              variant="outline"
              size="sm"
              onClick={onCloseReopen}
              className="w-full sm:w-auto bg-white"
            >
              Annuler
            </Button>
            <Button
              type="button"
              variant="primary"
              size="sm"
              onClick={onConfirmReopen}
              className="w-full sm:w-auto"
            >
              Rouvrir le signalement
            </Button>
          </div>
        </div>
      </Modal>

      {/* Confirmation modal on reject report */}
      <Modal
        isOpen={Boolean(reportToReject)}
        onClose={onCloseReject}
        title="Rejeter le signalement ?"
      >
        <div className="space-y-4 pt-1">
          <p className="text-sm text-slate-600 leading-relaxed">
            Êtes-vous sûr de vouloir classer sans suite le signalement{' '}
            <strong className="text-slate-900 font-semibold">
              #{reportToReject?.id.slice(-8)}
            </strong>
            {reportToReject?.reason ? (
              <>
                {' '}(motif :{' '}
                <span className="font-medium text-slate-800">
                  « {reportToReject.reason} »
                </span>
                )
              </>
            ) : null}
            {' '}? Le contenu restera en ligne et le signalement sera archivé
            comme clos dans l&apos;historique.
          </p>

          <div className="flex flex-col-reverse sm:flex-row items-center justify-end gap-2.5 pt-4 border-t border-slate-100">
            <Button
              type="button"
              variant="outline"
              size="sm"
              onClick={onCloseReject}
              className="w-full sm:w-auto bg-white"
            >
              Annuler
            </Button>
            <Button
              type="button"
              variant="secondary"
              size="sm"
              onClick={onConfirmReject}
              className="w-full sm:w-auto bg-slate-800 text-white hover:bg-slate-700"
            >
              Oui, rejeter le signalement
            </Button>
          </div>
        </div>
      </Modal>
    </>
  );
}
