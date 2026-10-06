'use client';

import { useActionState, useState } from 'react';
import { MAX_LISTING_BODY_LENGTH, MAX_LISTING_TITLE_LENGTH, MAX_PRICE } from "@/lib/limits";
import Link from 'next/link';
import { Button } from '@/components/ui/Button';
import { Modal } from '@/components/ui/Modal';
import { ImageUploadDropzone } from '@/components/listings/ImageUploadDropzone';
import { createListingAction } from './actions';
import { Card } from '@/components/ui/Card';
import { useCreateListing, CONDITIONS } from '@/hooks/useCreateListing';
import { AuthGuard } from '@/components/auth/AuthGuard';

function CreateListingContent() {
  const {
    formRef,
    categories,
    locations,
    selectedCategoryId,
    setSelectedCategoryId,
    isLoading,
    error,
    isCancelModalOpen,
    setIsCancelModalOpen,
    isObject,
    handleCancel,
    handleBackLink,
  } = useCreateListing();
  // the submit button waits for a photo that is still being sent
  const [isUploadingImage, setIsUploadingImage] = useState(false);

  const [formState, formAction, isSubmitting] = useActionState(createListingAction, { error: null });

  if (isLoading) {
    return (
      <main className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-12 text-sm text-gray-500">
        Chargement…
      </main>
    );
  }

  if (error) {
    return (
      <main className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-12 text-sm text-rose-600">
        {error}
      </main>
    );
  }

  return (
    <main className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8 sm:py-10">
      {/* Back navigation */}
      <nav className="mb-6 flex items-center gap-2 text-xs sm:text-sm text-slate-500">
        <Link
          href="/"
          onClick={handleBackLink}
          className="inline-flex items-center gap-1.5 font-medium text-slate-600 hover:text-[#00babc] transition-colors"
        >
          <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
            <path strokeLinecap="round" strokeLinejoin="round" d="M10.5 19.5L3 12m0 0l7.5-7.5M3 12h18" />
          </svg>
          <span>Retour aux annonces</span>
        </Link>
        <span className="text-slate-300">/</span>
        <span className="text-slate-800 font-medium">Nouvelle annonce</span>
      </nav>

      {/* Header */}
      <header className="mb-8">
        <h1 className="text-3xl sm:text-4xl font-extrabold text-slate-900 tracking-tight">
          Déposer une <span className="text-[#00babc]">annonce</span>
        </h1>
      </header>

      {/* Main form */}
      <form ref={formRef} action={formAction} className="space-y-8">
        {formState?.error && (
          <div
            role="alert"
            className="p-4 rounded-xl bg-rose-50 border border-rose-200 text-sm text-rose-700 font-medium flex items-center gap-3 shadow-xs"
          >
            <svg
              className="w-5 h-5 shrink-0 text-rose-500"
              fill="none"
              viewBox="0 0 24 24"
              stroke="currentColor"
              strokeWidth={2}
            >
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                d="M12 9v3.75m9-.75a9 9 0 11-18 0 9 9 0 0118 0zm-9 3.75h.008v.008H12v-.008z"
              />
            </svg>
            <span>{formState.error}</span>
          </div>
        )}
        {/* Card 1: Essential details */}
        <Card className="space-y-6">
          <h2 className="text-lg font-bold text-slate-900 border-b border-slate-100 pb-3 flex items-center gap-2">
            <svg className="w-5 h-5 text-[#00babc]" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M11.25 11.25l.041-.02a.75.75 0 011.063.852l-.708 2.836a.75.75 0 001.063.853l.041-.021M21 12a9 9 0 11-18 0 9 9 0 0118 0zm-9-3.75h.008v.008H12V8.25z" />
            </svg>
            Informations générales
          </h2>

          {/* Title */}
          <div>
            <label htmlFor="title" className="block text-xs font-semibold text-slate-700 uppercase tracking-wider mb-2">
              Titre de l&apos;annonce <span className="text-rose-500">*</span>
            </label>
            <input
              type="text"
              id="title"
              name="title"
              maxLength={MAX_LISTING_TITLE_LENGTH}
              required
              className="w-full px-4 py-2.5 rounded-xl bg-slate-50/50 border border-slate-200 text-slate-900 text-sm placeholder:text-slate-400 focus:outline-hidden focus:bg-white focus:border-[#00babc] focus:ring-2 focus:ring-[#00babc]/20 transition-all"
            />
          </div>

          {/* Price & Category */}
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-6">
            {/* Price */}
            <div>
              <label htmlFor="price" className="block text-xs font-semibold text-slate-700 uppercase tracking-wider mb-2">
                Prix (€) <span className="text-rose-500">*</span>
              </label>
              <div className="relative">
                <input
                  type="number"
                  id="price"
                  name="price"
                  min="0"
                  max={MAX_PRICE}
                  step="1"
                  required
                  className="w-full pl-4 pr-10 py-2.5 rounded-xl bg-slate-50/50 border border-slate-200 text-slate-900 text-sm placeholder:text-slate-400 focus:outline-hidden focus:bg-white focus:border-[#00babc] focus:ring-2 focus:ring-[#00babc]/20 transition-all"
                />
                <span className="absolute right-3.5 top-1/2 -translate-y-1/2 text-sm font-bold text-slate-400">
                  €
                </span>
              </div>
              <p className="text-xs text-slate-500 mt-1">Indiquez 0 pour un don / gratuit.</p>
            </div>

            {/* Category */}
            <div>
              <label htmlFor="category_id" className="block text-xs font-semibold text-slate-700 uppercase tracking-wider mb-2">
                Catégorie <span className="text-rose-500">*</span>
              </label>
              <select
                id="category_id"
                name="category_id"
                required
                value={selectedCategoryId}
                onChange={(e) => setSelectedCategoryId(e.target.value)}
                className="w-full px-4 py-2.5 rounded-xl bg-slate-50/50 border border-slate-200 text-slate-900 text-sm focus:outline-hidden focus:bg-white focus:border-[#00babc] focus:ring-2 focus:ring-[#00babc]/20 transition-all"
              >
                {categories.map((category) => (
                  <option key={category.id} value={category.id}>
                    {category.category_name}
                  </option>
                ))}
              </select>
            </div>
          </div>

          {/* Location */}
          <div>
            <label htmlFor="location_id" className="block text-xs font-semibold text-slate-700 uppercase tracking-wider mb-2">
              Lieu d&apos;échange / Campus <span className="text-rose-500">*</span>
            </label>
            <select
              id="location_id"
              name="location_id"
              required
              defaultValue={locations[0]?.id}
              className="w-full px-4 py-2.5 rounded-xl bg-slate-50/50 border border-slate-200 text-slate-900 text-sm focus:outline-hidden focus:bg-white focus:border-[#00babc] focus:ring-2 focus:ring-[#00babc]/20 transition-all"
            >
              {locations.map((location) => (
                <option key={location.id} value={location.id}>
                  {location.location}
                </option>
              ))}
            </select>
          </div>
        </Card>

        {/* Card 2: Item condition (only for physical objects) */}
        {isObject && (
          <Card className="space-y-6">
            <h2 className="text-lg font-bold text-slate-900 border-b border-slate-100 pb-3 flex items-center gap-2">
              <svg className="w-5 h-5 text-[#00babc]" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                <path strokeLinecap="round" strokeLinejoin="round" d="M9 12.75L11.25 15 15 9.75M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
              </svg>
              État du produit <span className="text-rose-500">*</span>
            </h2>

            <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-3 gap-3">
              {CONDITIONS.map((cond, idx) => (
                <label
                  key={cond.value}
                  className="relative flex items-center p-3 rounded-xl border border-slate-200 cursor-pointer hover:border-slate-300 transition-all has-checked:border-[#00babc] has-checked:bg-[#00babc]/5 has-checked:shadow-xs"
                >
                  <input
                    type="radio"
                    name="condition"
                    value={cond.value}
                    defaultChecked={idx === 1}
                    className="w-4 h-4 text-[#00babc] border-slate-300 focus:ring-[#00babc] accent-[#00babc]"
                  />
                  <span className="ml-2.5 text-xs sm:text-sm font-medium text-slate-800">
                    {cond.label}
                  </span>
                </label>
              ))}
            </div>
          </Card>
        )}

        {/* Card 3: Description & Photo */}
        <Card className="space-y-6">
          <h2 className="text-lg font-bold text-slate-900 border-b border-slate-100 pb-3 flex items-center gap-2">
            <svg className="w-5 h-5 text-[#00babc]" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M3.75 6.75h16.5M3.75 12h16.5m-16.5 5.25H12" />
            </svg>
            Description & Photo(s)
          </h2>

          {/* Description */}
          <div>
            <label htmlFor="body" className="block text-xs font-semibold text-slate-700 uppercase tracking-wider mb-2">
              Description de l&apos;article <span className="text-rose-500">*</span>
            </label>
            <textarea
              id="body"
              name="body"
              maxLength={MAX_LISTING_BODY_LENGTH}
              rows={5}
              required
              placeholder="Décrivez l'annonce, ce qui est inclus (câbles, boîte d'origine, facture), la raison de la vente et vos disponibilités sur le campus..."
              className="w-full px-4 py-3 rounded-xl bg-slate-50/50 border border-slate-200 text-slate-900 text-sm placeholder:text-slate-400 focus:outline-hidden focus:bg-white focus:border-[#00babc] focus:ring-2 focus:ring-[#00babc]/20 transition-all resize-y"
            ></textarea>
          </div>

          {/* Photo Dropzone & Preview */}
          <div>
            <label className="block text-xs font-semibold text-slate-700 uppercase tracking-wider mb-2">
              Photo(s) du produit (Optionnel)
            </label>
            <ImageUploadDropzone
              name="image_data"
              categoryPlaceholder="true"
              onUploadingChange={setIsUploadingImage}
            />
            <p className="text-xs text-slate-500 mt-2">
              Téléversez une photo depuis votre appareil ou collez une capture d&apos;écran (Ctrl+V). Si aucune photo n&apos;est fournie, une illustration adaptée à la catégorie sera attribuée automatiquement.
            </p>
          </div>
        </Card>

        {/* Action buttons */}
        <div className="flex flex-col-reverse sm:flex-row items-center justify-end gap-3 pt-4">
          <Button
            type="button"
            variant="outline"
            size="lg"
            onClick={handleCancel}
            className="w-full sm:w-auto bg-white"
          >
            Annuler
          </Button>

          <Button
            type="submit"
            variant="primary"
            size="lg"
            className="w-full sm:w-auto"
            isLoading={isSubmitting}
            disabled={isSubmitting || isUploadingImage}
          >
            <svg className="w-4 h-4 stroke-slate-950" fill="none" viewBox="0 0 24 24" strokeWidth={2.5}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M12 4.5v15m7.5-7.5h-15" />
            </svg>
            <span>Publier l&apos;annonce</span>
          </Button>
        </div>
      </form>

      {/* Confirmation modal on cancel */}
      <Modal
        isOpen={isCancelModalOpen}
        onClose={() => setIsCancelModalOpen(false)}
        title="Abandonner l'annonce ?"
      >
        <div className="space-y-4 pt-1">
          <p className="text-sm text-slate-600 leading-relaxed">
            Êtes-vous sûr de vouloir annuler la création de cette annonce ? Toutes les informations saisies seront perdues.
          </p>
          <div className="flex flex-col-reverse sm:flex-row items-center justify-end gap-2.5 pt-4 border-t border-slate-100">
            <Button
              type="button"
              variant="outline"
              size="sm"
              onClick={() => setIsCancelModalOpen(false)}
              className="w-full sm:w-auto bg-white"
            >
              Continuer la saisie
            </Button>
            <Button
              href="/"
              variant="danger"
              size="sm"
              className="w-full sm:w-auto"
            >
              Oui, abandonner
            </Button>
          </div>
        </div>
      </Modal>
    </main>
  );
}

export default function CreateListingPage() {
  return (
    <AuthGuard>
      <CreateListingContent />
    </AuthGuard>
  );
}