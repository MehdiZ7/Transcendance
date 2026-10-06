'use client';

import React, { useState, useRef, useCallback } from 'react';
import Image from 'next/image';
import { isUnoptimizedImage } from '@/lib/images';
import { uploadsApi } from '@/lib/api/uploads';

interface ImageUploadDropzoneProps {
  name?: string;
  defaultValue?: string;
  categoryPlaceholder?: string;
  onChange?: (imagePath: string | null) => void;
  // lets the form hold its submit button while a file is being sent
  onUploadingChange?: (uploading: boolean) => void;
  className?: string;
}

const MAX_FILE_SIZE_BYTES = 5 * 1024 * 1024; // 5 MB
const ACCEPTED_TYPES = ['image/jpeg', 'image/png', 'image/webp', 'image/gif'];

function formatFileSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} Ko`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} Mo`;
}

export function ImageUploadDropzone({
  name = 'image_data',
  defaultValue = '',
  categoryPlaceholder,
  onChange,
  onUploadingChange,
  className = '',
}: ImageUploadDropzoneProps) {
  const [imagePreview, setImagePreview] = useState<string | null>(defaultValue || null);
  const [fileName, setFileName] = useState<string | null>(null);
  const [fileSize, setFileSize] = useState<number | null>(null);
  const [isDragging, setIsDragging] = useState(false);
  const [isUploading, setIsUploading] = useState(false);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  const fileInputRef = useRef<HTMLInputElement>(null);
  // Only the most recent selection's response should ever reach state -
  // a slower response for a file the user already moved on from must lose.
  const uploadIdRef = useRef(0);

  // Sync state during render when defaultValue prop changes
  const [prevDefaultValue, setPrevDefaultValue] = useState(defaultValue);
  if (defaultValue !== prevDefaultValue) {
    setPrevDefaultValue(defaultValue);
    if (defaultValue) {
      setImagePreview(defaultValue);
    }
  }

  const processFile = useCallback(
    (file: File) => {
      setErrorMessage(null);

      // Validate file type
      if (!ACCEPTED_TYPES.includes(file.type)) {
        setErrorMessage(
          'Format non supporté. Veuillez choisir une image PNG, JPG, WEBP ou GIF.'
        );
        return;
      }

      // Validate file size
      if (file.size > MAX_FILE_SIZE_BYTES) {
        setErrorMessage(
          `Image trop volumineuse (${formatFileSize(file.size)}). La taille maximale autorisée est de 5 Mo.`
        );
        return;
      }

      // The file goes to the server now; what the form keeps is the path it answers
      const uploadId = ++uploadIdRef.current;
      setIsUploading(true);
      onUploadingChange?.(true);
      uploadsApi
        .uploadImage(file)
        .then((path) => {
          if (uploadIdRef.current !== uploadId) return;
          setImagePreview(path);
          setFileName(file.name);
          setFileSize(file.size);
          onChange?.(path);
        })
        .catch((err: unknown) => {
          if (uploadIdRef.current !== uploadId) return;
          setErrorMessage(
            err instanceof Error ? err.message : "Échec de l'envoi de l'image. Réessayez."
          );
        })
        .finally(() => {
          if (uploadIdRef.current !== uploadId) return;
          setIsUploading(false);
          onUploadingChange?.(false);
        });
    },
    [onChange, onUploadingChange]
  );

  const handleDragEnter = (e: React.DragEvent<HTMLDivElement>) => {
    e.preventDefault();
    e.stopPropagation();
    setIsDragging(true);
  };

  const handleDragLeave = (e: React.DragEvent<HTMLDivElement>) => {
    e.preventDefault();
    e.stopPropagation();
    setIsDragging(false);
  };

  const handleDragOver = (e: React.DragEvent<HTMLDivElement>) => {
    e.preventDefault();
    e.stopPropagation();
    if (!isDragging) setIsDragging(true);
  };

  const handleDrop = (e: React.DragEvent<HTMLDivElement>) => {
    e.preventDefault();
    e.stopPropagation();
    setIsDragging(false);

    if (e.dataTransfer.files && e.dataTransfer.files.length > 0) {
      const file = e.dataTransfer.files[0];
      processFile(file);
    }
  };

  const handleFileInputChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    if (e.target.files && e.target.files.length > 0) {
      const file = e.target.files[0];
      processFile(file);
    }
  };

  const handlePaste = (e: React.ClipboardEvent<HTMLDivElement>) => {
    if (e.clipboardData.files && e.clipboardData.files.length > 0) {
      const file = e.clipboardData.files[0];
      if (ACCEPTED_TYPES.includes(file.type)) {
        e.preventDefault();
        processFile(file);
      }
    }
  };

  const handleRemove = (e: React.MouseEvent) => {
    e.stopPropagation();
    setImagePreview(null);
    setFileName(null);
    setFileSize(null);
    setErrorMessage(null);
    if (fileInputRef.current) {
      fileInputRef.current.value = '';
    }
    onChange?.(null);
  };

  return (
    <div className={`space-y-3 ${className}`} onPaste={handlePaste}>
      {/* Hidden input passing the image path / URL to the parent form */}
      <input type="hidden" name={name} value={imagePreview || ''} />

      {/* File input (hidden) */}
      <input
        ref={fileInputRef}
        type="file"
        accept="image/png,image/jpeg,image/webp,image/gif"
        className="sr-only"
        onChange={handleFileInputChange}
      />

      {/* Main Area */}
      {!imagePreview ? (
        <div>
          <div
            onClick={() => fileInputRef.current?.click()}
            onDragEnter={handleDragEnter}
            onDragLeave={handleDragLeave}
            onDragOver={handleDragOver}
            onDrop={handleDrop}
            tabIndex={0}
            role="button"
            onKeyDown={(e) => {
              if (e.key === 'Enter' || e.key === ' ') {
                e.preventDefault();
                fileInputRef.current?.click();
              }
            }}
            className={`group relative flex flex-col items-center justify-center p-8 rounded-2xl border-2 border-dashed transition-all cursor-pointer select-none outline-hidden ${
              isDragging
                ? 'border-[#00babc] bg-[#00babc]/10 scale-[0.99]'
                : 'border-slate-300 hover:border-[#00babc] bg-slate-50/70 hover:bg-slate-50'
            }`}
          >
            {/* Center Upload Icon */}
            <div
              className={`w-14 h-14 rounded-2xl flex items-center justify-center mb-4 transition-transform group-hover:scale-110 ${
                isDragging
                  ? 'bg-[#00babc] text-slate-950 shadow-lg shadow-[#00babc]/30'
                  : 'bg-white text-slate-600 border border-slate-200 group-hover:text-[#00babc] group-hover:border-[#00babc]/40 shadow-xs'
              }`}
            >
              <svg
                className="w-7 h-7"
                fill="none"
                viewBox="0 0 24 24"
                stroke="currentColor"
                strokeWidth={1.75}
              >
                <path
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  d="M12 16.5V9.75m0 0l3 3m-3-3l-3 3M6.75 19.5a4.5 4.5 0 01-1.41-8.775 5.25 5.25 0 0110.233-2.33 3 3 0 013.758 3.848A3.752 3.752 0 0118 19.5H6.75z"
                />
              </svg>
            </div>

            <p className="text-sm font-semibold text-slate-800 text-center">
              <span className="text-[#008e90] group-hover:underline">
                Cliquez pour choisir un fichier
              </span>{' '}
              ou glissez-déposez ici
            </p>
            <p className="text-xs text-slate-500 mt-1 text-center">
              PNG, JPG, WEBP ou GIF (Max 5 Mo) • Vous pouvez aussi coller une capture d&apos;écran (Ctrl+V)
            </p>

            {categoryPlaceholder && (
              <div className="mt-4 inline-flex items-center gap-1.5 px-3 py-1 rounded-full bg-slate-200/60 text-slate-600 text-[11px]">
                <span>💡 Optionnel : sans photo, une illustration sera assignée</span>
              </div>
            )}
          </div>
        </div>
      ) : (
        /* Image Preview State */
        <div className="relative rounded-2xl border border-slate-200 bg-slate-900 overflow-hidden shadow-sm group">
          <div className="relative aspect-[16/10] w-full max-h-[360px]">
            <Image
              src={imagePreview}
              alt="Aperçu de la photo de l'annonce"
              fill
              sizes="(max-width: 1024px) 100vw, 800px"
              unoptimized={isUnoptimizedImage(imagePreview)}
              className="object-cover"
            />

            {/* Gradient Overlay for controls */}
            <div className="absolute inset-0 bg-gradient-to-t from-slate-950/80 via-transparent to-slate-950/40 pointer-events-none" />

            {/* Top Badge: Mock Ready / Upload Status */}
            <div className="absolute top-3 left-3">
              <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full bg-emerald-500/90 text-slate-950 text-xs font-bold tracking-tight shadow-xs backdrop-blur-xs">
                <span className="w-1.5 h-1.5 rounded-full bg-slate-950 animate-pulse" />
                Photo prête
              </span>
            </div>

            {/* Top Right Action: Remove Button */}
            <div className="absolute top-3 right-3">
              <button
                type="button"
                onClick={handleRemove}
                title="Supprimer la photo"
                className="w-8 h-8 rounded-full bg-slate-900/80 hover:bg-rose-600 text-white flex items-center justify-center transition-colors shadow-md backdrop-blur-xs cursor-pointer"
              >
                <svg
                  className="w-4 h-4"
                  fill="none"
                  viewBox="0 0 24 24"
                  stroke="currentColor"
                  strokeWidth={2}
                >
                  <path
                    strokeLinecap="round"
                    strokeLinejoin="round"
                    d="M6 18L18 6M6 6l12 12"
                  />
                </svg>
              </button>
            </div>

            {/* Bottom Bar: Filename, size & Replace button */}
            <div className="absolute bottom-3 inset-x-3 flex items-center justify-between gap-2 text-white">
              <div className="truncate max-w-[65%]">
                <p className="text-xs font-semibold truncate drop-shadow-xs">
                  {fileName || 'Photo sélectionnée'}
                </p>
                {fileSize && (
                  <p className="text-[10px] text-slate-300">
                    {formatFileSize(fileSize)}
                  </p>
                )}
              </div>

              <button
                type="button"
                onClick={() => fileInputRef.current?.click()}
                className="inline-flex items-center gap-1 px-3 py-1.5 rounded-lg bg-white/20 hover:bg-white/30 text-white text-xs font-semibold backdrop-blur-xs border border-white/30 transition-colors cursor-pointer shrink-0"
              >
                <svg
                  className="w-3.5 h-3.5"
                  fill="none"
                  viewBox="0 0 24 24"
                  stroke="currentColor"
                  strokeWidth={2}
                >
                  <path
                    strokeLinecap="round"
                    strokeLinejoin="round"
                    d="M16.023 9.348h4.992v-.001M2.985 19.644v-4.992m0 0h4.992m-4.993 0l3.181 3.183a8.25 8.25 0 0013.803-3.7M4.031 9.865a8.25 8.25 0 0113.803-3.7l3.181 3.182m0-4.991v4.99"
                  />
                </svg>
                <span>Changer</span>
              </button>
            </div>
          </div>
        </div>
      )}

      {isUploading && (
        <p role="status" className="text-xs font-medium text-slate-600">
          Envoi de l&apos;image en cours…
        </p>
      )}

      {/* Error Feedback */}
      {errorMessage && (
        <div className="flex items-center gap-2 p-3 rounded-xl bg-rose-50 border border-rose-200 text-rose-700 text-xs font-medium">
          <svg
            className="w-4 h-4 shrink-0"
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
          <span>{errorMessage}</span>
        </div>
      )}
    </div>
  );
}
