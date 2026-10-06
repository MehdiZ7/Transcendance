'use client';

import React, { useState, useRef, useCallback } from 'react';
import Image from 'next/image';
import { isUnoptimizedImage } from '@/lib/images';
import { uploadsApi } from '@/lib/api/uploads';

interface AvatarUploadDropzoneProps {
  name?: string;
  defaultValue?: string;
  onChange?: (path: string | null) => void;
  // lets the form hold its submit button while a file is being sent
  onUploadingChange?: (uploading: boolean) => void;
  className?: string;
}

const MAX_FILE_SIZE_BYTES = 5 * 1024 * 1024; // 5 Mo
const ACCEPTED_TYPES = ['image/jpeg', 'image/png', 'image/webp', 'image/gif'];

export function AvatarUploadDropzone({
  name = 'avatar_url',
  defaultValue = '',
  onChange,
  onUploadingChange,
  className = '',
}: AvatarUploadDropzoneProps) {
  const [imagePreview, setImagePreview] = useState<string | null>(defaultValue || null);
  const [isDragging, setIsDragging] = useState(false);
  const [isUploading, setIsUploading] = useState(false);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  const fileInputRef = useRef<HTMLInputElement>(null);
  // Only the most recent selection's response should ever reach state -
  // a slower response for a file the user already moved on from must lose.
  const uploadIdRef = useRef(0);

  // Sync when defaultValue changes from the parent
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

      if (!ACCEPTED_TYPES.includes(file.type)) {
        setErrorMessage('Format non supporté (PNG, JPG, WEBP, GIF).');
        return;
      }

      if (file.size > MAX_FILE_SIZE_BYTES) {
        setErrorMessage('Image trop volumineuse (max 5 Mo).');
        return;
      }

      // The file goes to the server; what the profile keeps is the path it answers
      const uploadId = ++uploadIdRef.current;
      setIsUploading(true);
      onUploadingChange?.(true);
      uploadsApi
        .uploadImage(file)
        .then((path) => {
          if (uploadIdRef.current !== uploadId) return;
          setImagePreview(path);
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

  return (
    <div className={`flex flex-col items-center gap-2 ${className}`}>
      <input type="hidden" name={name} value={imagePreview || ''} />

      <input
        ref={fileInputRef}
        type="file"
        accept="image/png,image/jpeg,image/webp,image/gif"
        className="sr-only"
        onChange={handleFileInputChange}
      />

      {/* Zone Circulaire Droppable / Cliquable */}
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
        className={`group relative w-28 h-28 rounded-full cursor-pointer select-none overflow-hidden transition-all duration-200 outline-none ${
          isDragging
            ? 'ring-4 ring-[#00babc] ring-offset-2 scale-105'
            : 'hover:ring-4 hover:ring-[#00babc]/30'
        }`}
      >
        {/* Profile photo or default avatar */}
        {imagePreview ? (
          <Image
            src={imagePreview}
            alt="Avatar utilisateur"
            fill
            sizes="128px"
            unoptimized={isUnoptimizedImage(imagePreview)}
            className="object-cover"
          />
        ) : (
          <div className="w-full h-full bg-slate-200 flex items-center justify-center text-slate-400">
            <svg
              className="w-14 h-14"
              fill="currentColor"
              viewBox="0 0 24 24"
            >
              <path d="M24 20.993V24H0v-2.996A14.977 14.977 0 0112.004 15c4.904 0 9.26 2.354 11.996 5.993zM16.002 8.999a4 4 0 11-8 0 4 4 0 018 0z" />
            </svg>
          </div>
        )}

        {/* Hover overlay */}
        <div className="absolute inset-0 bg-slate-950/60 opacity-0 group-hover:opacity-100 transition-opacity duration-200 flex flex-col items-center justify-center text-white backdrop-blur-[1px]">
          <svg
            className="w-6 h-6 mb-1 text-white/90"
            fill="none"
            viewBox="0 0 24 24"
            stroke="currentColor"
            strokeWidth={2}
          >
            <path
              strokeLinecap="round"
              strokeLinejoin="round"
              d="M6.827 6.175A2.31 2.31 0 015.186 7.23c-.38.054-.757.112-1.134.175C2.999 7.58 2.25 8.507 2.25 9.574V18a2.25 2.25 0 002.25 2.25h15A2.25 2.25 0 0021.75 18V9.574c0-1.067-.75-1.994-1.802-2.169a47.865 47.865 0 00-1.134-.175 2.31 2.31 0 01-1.64-1.055l-.822-1.316a2.192 2.192 0 00-1.736-1.039 48.774 48.774 0 00-5.232 0 2.192 2.192 0 00-1.736 1.039l-.821 1.316z"
            />
            <path
              strokeLinecap="round"
              strokeLinejoin="round"
              d="M16.5 12.75a4.5 4.5 0 11-9 0 4.5 4.5 0 019 0z"
            />
          </svg>
          <span className="text-[10px] font-semibold tracking-wide uppercase">
            Modifier
          </span>
        </div>
      </div>

      {/* Error message under the avatar */}
      {isUploading && (
        <p role="status" className="text-xs font-medium text-slate-600 text-center">
          Envoi de l&apos;image…
        </p>
      )}

      {errorMessage && (
        <p className="text-xs text-rose-600 font-medium text-center max-w-[200px]">
          {errorMessage}
        </p>
      )}
    </div>
  );
}
