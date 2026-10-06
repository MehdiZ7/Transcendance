'use client';

import React, { useState } from 'react';
import Button from '@/components/ui/Button';
import { Modal } from '@/components/ui/Modal';
import { MAX_PRICE } from '@/lib/limits';
import type { Category } from '@/types/listing';

export type SortOption = 'recent' | 'oldest' | 'price_asc' | 'price_desc' | 'likes_desc';

export interface FilterModalContentProps {
  categories?: Category[];
  initialCategory?: string;
  initialSort?: string;
  initialMinPrice?: string;
  initialMaxPrice?: string;
  onApply: (filters: { category?: string; sort?: string; minPrice?: string; maxPrice?: string }) => void;
  onReset: () => void;
  onClose: () => void;
}

const SORT_OPTIONS: { value: SortOption; label: string; }[] = [
  { value: 'recent', label: 'Plus récentes'},
  { value: 'oldest', label: 'Plus anciennes'},
  { value: 'price_asc', label: 'Prix : croissant'},
  { value: 'price_desc', label: 'Prix : décroissant'},
  { value: 'likes_desc', label: 'Plus populaires'},
];

const PRICE_PRESETS: { label: string; min?: number; max?: number }[] = [
  { label: 'Gratuit (0€)', min: 0, max: 0 },
  { label: '< 30 €', min: undefined, max: 30 },
  { label: '30 € - 100 €', min: 30, max: 100 },
  { label: '100 € - 300 €', min: 100, max: 300 },
  { label: '> 300 €', min: 300, max: undefined },
];

export function FilterModalContent({
  categories = [],
  initialCategory = '',
  initialSort = 'recent',
  initialMinPrice = '',
  initialMaxPrice = '',
  onApply,
  onReset,
  onClose,
}: FilterModalContentProps) {
  const [selectedCategory, setSelectedCategory] = useState<string>(initialCategory);
  const [selectedSort, setSelectedSort] = useState<string>(initialSort);
  const [minPrice, setMinPrice] = useState<string>(initialMinPrice);
  const [maxPrice, setMaxPrice] = useState<string>(initialMaxPrice);
  const [isConfirmResetOpen, setIsConfirmResetOpen] = useState(false);

  const handlePresetClick = (presetMin?: number, presetMax?: number) => {
    setMinPrice(presetMin !== undefined ? String(presetMin) : '');
    setMaxPrice(presetMax !== undefined ? String(presetMax) : '');
  };

  // Drop non-numeric prices, clamp the rest to the API's MAX_PRICE.
  const clampPrice = (value: string): string | undefined => {
    const trimmed = value.trim();
    if (!trimmed) return undefined;
    const parsed = Number(trimmed);
    if (!Number.isFinite(parsed) || parsed < 0) return undefined;
    return String(Math.min(Math.trunc(parsed), MAX_PRICE));
  };

  const handleApply = (e: React.FormEvent) => {
    e.preventDefault();
    onApply({
      category: selectedCategory || undefined,
      sort: selectedSort,
      minPrice: clampPrice(minPrice),
      maxPrice: clampPrice(maxPrice),
    });
  };

  const handleReset = () => {
    setIsConfirmResetOpen(true);
  };

  const handleConfirmReset = () => {
    setSelectedCategory('');
    setSelectedSort('recent');
    setMinPrice('');
    setMaxPrice('');
    setIsConfirmResetOpen(false);
    onReset();
  };

  const hasActiveFilters = Boolean(
    selectedCategory ||
    (selectedSort && selectedSort !== 'recent') ||
    minPrice.trim() ||
    maxPrice.trim()
  );

  return (
    <form onSubmit={handleApply} className="space-y-6 pt-1">
      {/* 1. Categories */}
      {categories.length > 0 && (
        <div>
          <label className="block text-xs font-semibold text-slate-700 uppercase tracking-wider mb-3">
            Catégorie
          </label>
          <div className="flex flex-wrap gap-2">
            <button
              type="button"
              onClick={() => setSelectedCategory('')}
              className={`px-3.5 py-2 rounded-xl text-xs sm:text-sm font-semibold transition-all cursor-pointer border ${
                !selectedCategory
                  ? 'border-[#00babc] bg-[#00babc] text-slate-950 shadow-xs'
                  : 'border-slate-200 hover:border-slate-300 hover:bg-slate-50 text-slate-700 bg-white'
              }`}
            >
              Toutes les catégories
            </button>
            {categories.map((cat) => {
              const isSelected = selectedCategory === cat.id;
              return (
                <button
                  key={cat.id}
                  type="button"
                  onClick={() => setSelectedCategory(isSelected ? '' : cat.id)}
                  className={`px-3.5 py-2 rounded-xl text-xs sm:text-sm font-semibold transition-all cursor-pointer border ${
                    isSelected
                      ? 'border-[#00babc] bg-[#00babc] text-slate-950 shadow-xs'
                      : 'border-slate-200 hover:border-slate-300 hover:bg-slate-50 text-slate-700 bg-white'
                  }`}
                >
                  {cat.category_name}
                </button>
              );
            })}
          </div>
        </div>
      )}

      {/* 2. Tri (Sorting) */}
      <div className={categories.length > 0 ? "border-t border-slate-100 pt-5" : ""}>
        <label className="block text-xs font-semibold text-slate-700 uppercase tracking-wider mb-3">
          Trier les annonces
        </label>
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
          {SORT_OPTIONS.map((option) => {
            const isSelected = selectedSort === option.value;
            return (
              <label
                key={option.value}
                className={`flex items-center gap-3 p-3 rounded-xl border cursor-pointer transition-all ${
                  isSelected
                    ? 'border-[#00babc] bg-[#00babc]/5 shadow-xs font-semibold text-slate-900'
                    : 'border-slate-200 hover:border-slate-300 hover:bg-slate-50 text-slate-700 font-medium'
                }`}
              >
                <input
                  type="radio"
                  name="sort"
                  value={option.value}
                  checked={isSelected}
                  onChange={() => setSelectedSort(option.value)}
                  className="w-4 h-4 text-[#00babc] border-slate-300 focus:ring-[#00babc] accent-[#00babc]"
                />
                <span className="text-xs sm:text-sm">{option.label}</span>
              </label>
            );
          })}
        </div>
      </div>

      {/* 2. Fourchette de prix (Price range) */}
      <div className="border-t border-slate-100 pt-5 space-y-3">
        <label className="block text-xs font-semibold text-slate-700 uppercase tracking-wider">
          Fourchette de prix (€)
        </label>

        {/* Inputs min / max */}
        <div className="grid grid-cols-2 gap-3 items-center">
          <div>
            <label htmlFor="modal_min_price" className="block text-[11px] text-slate-500 mb-1">
              Prix minimum
            </label>
            <div className="relative">
              <input
                id="modal_min_price"
                type="number"
                min="0"
                max={MAX_PRICE}
                step="1"
                placeholder="0"
                value={minPrice}
                onChange={(e) => setMinPrice(e.target.value)}
                className="w-full pl-3 pr-8 py-2 text-sm bg-slate-50 border border-slate-200 rounded-xl text-slate-900 placeholder:text-slate-400 focus:outline-hidden focus:bg-white focus:border-[#00babc] transition-all"
              />
              <span className="absolute right-3 top-1/2 -translate-y-1/2 text-xs font-bold text-slate-400">
                €
              </span>
            </div>
          </div>

          <div>
            <label htmlFor="modal_max_price" className="block text-[11px] text-slate-500 mb-1">
              Prix maximum
            </label>
            <div className="relative">
              <input
                id="modal_max_price"
                type="number"
                min="0"
                max={MAX_PRICE}
                step="1"
                placeholder="ex: 250"
                value={maxPrice}
                onChange={(e) => setMaxPrice(e.target.value)}
                className="w-full pl-3 pr-8 py-2 text-sm bg-slate-50 border border-slate-200 rounded-xl text-slate-900 placeholder:text-slate-400 focus:outline-hidden focus:bg-white focus:border-[#00babc] transition-all"
              />
              <span className="absolute right-3 top-1/2 -translate-y-1/2 text-xs font-bold text-slate-400">
                €
              </span>
            </div>
          </div>
        </div>

        {/* Presets */}
        <div>
          <span className="text-[11px] text-slate-400 block mb-1.5">Raccourcis rapides :</span>
          <div className="flex flex-wrap gap-1.5">
            {PRICE_PRESETS.map((preset) => (
              <button
                key={preset.label}
                type="button"
                onClick={() => handlePresetClick(preset.min, preset.max)}
                className="px-2.5 py-1 rounded-lg bg-slate-100 hover:bg-slate-200 text-slate-700 text-xs font-medium transition-colors cursor-pointer"
              >
                {preset.label}
              </button>
            ))}
          </div>
        </div>
      </div>

      {/* Footer buttons */}
      <div className="flex flex-col-reverse sm:flex-row items-center justify-between gap-3 pt-5 border-t border-slate-100">
        <div>
          {hasActiveFilters && (
            <button
              type="button"
              onClick={handleReset}
              className="text-xs font-semibold text-rose-600 hover:text-rose-700 hover:underline cursor-pointer"
            >
              Réinitialiser le tri et les prix
            </button>
          )}
        </div>

        <div className="flex items-center gap-2 w-full sm:w-auto justify-end">
          <Button
            type="button"
            variant="outline"
            size="sm"
            onClick={onClose}
            className="w-full sm:w-auto bg-white"
          >
            Fermer
          </Button>
          <Button
            type="submit"
            variant="primary"
            size="sm"
            className="w-full sm:w-auto"
          >
            Appliquer
          </Button>
        </div>
      </div>

      {/* Confirmation modal before resetting advanced filters */}
      <Modal
        isOpen={isConfirmResetOpen}
        onClose={() => setIsConfirmResetOpen(false)}
        title="Réinitialiser les options ?"
      >
        <div className="space-y-4 pt-1">
          <p className="text-sm text-slate-600 leading-relaxed">
            Êtes-vous sûr de vouloir réinitialiser le tri et la fourchette de prix ?
          </p>
          <div className="flex flex-col-reverse sm:flex-row items-center justify-end gap-2.5 pt-4 border-t border-slate-100">
            <Button
              type="button"
              variant="outline"
              size="sm"
              onClick={() => setIsConfirmResetOpen(false)}
              className="w-full sm:w-auto bg-white"
            >
              Annuler
            </Button>
            <Button
              type="button"
              variant="danger"
              size="sm"
              onClick={handleConfirmReset}
              className="w-full sm:w-auto"
            >
              Oui, réinitialiser
            </Button>
          </div>
        </div>
      </Modal>
    </form>
  );
}

export default FilterModalContent;
