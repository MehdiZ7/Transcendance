'use client';

import React, { useState } from 'react';
import { useRouter } from 'next/navigation';
import Button from '@/components/ui/Button';
import { Modal } from '@/components/ui/Modal';
import SearchBar from '@/components/ui/SearchBar';
import FilterModalContent from './FilterModalContent';
import ResetFiltersButton from './ResetFiltersButton';
import type { Category, Location } from '@/types/listing';

export interface FilterBarProps {
  categories: Category[];
  locations: Location[];
  selectedCategory?: string;
  selectedLocation?: string;
  selectedSort?: string;
  minPrice?: string;
  maxPrice?: string;
  query?: string;
  totalResults: number;
}

export function FilterBar({
  categories,
  locations,
  selectedCategory,
  selectedLocation,
  selectedSort = 'recent',
  minPrice,
  maxPrice,
  query,
  totalResults,
}: FilterBarProps) {
  const router = useRouter();
  const [isFilterModalOpen, setIsFilterModalOpen] = useState(false);

  // Helper to construct query string with updated filters
  const buildUrl = (newParams: {
    q?: string;
    category?: string;
    location?: string;
    sort?: string;
    minPrice?: string;
    maxPrice?: string;
  }) => {
    const params = new URLSearchParams();
    const finalQ = newParams.q !== undefined ? newParams.q : query;
    const finalCat = newParams.category !== undefined ? newParams.category : selectedCategory;
    const finalLoc = newParams.location !== undefined ? newParams.location : selectedLocation;
    const finalSort = newParams.sort !== undefined ? newParams.sort : selectedSort;
    const finalMin = newParams.minPrice !== undefined ? newParams.minPrice : minPrice;
    const finalMax = newParams.maxPrice !== undefined ? newParams.maxPrice : maxPrice;

    if (finalQ) params.set('q', finalQ);
    if (finalCat) params.set('category', finalCat);
    if (finalLoc) params.set('location', finalLoc);
    if (finalSort && finalSort !== 'recent') params.set('sort', finalSort);
    if (finalMin) params.set('minPrice', finalMin);
    if (finalMax) params.set('maxPrice', finalMax);

    const queryString = params.toString();
    return queryString ? `/?${queryString}` : '/';
  };

  const handleLocationChange = (e: React.ChangeEvent<HTMLSelectElement>) => {
    const locId = e.target.value || undefined;
    router.push(buildUrl({ location: locId || '' }));
  };

  const handleSearch = (newQuery: string) => {
    const trimmed = newQuery.trim() || undefined;
    router.push(buildUrl({ q: trimmed || '' }));
  };

  // Count active modal filters (category, sort != recent, minPrice, maxPrice)
  const activeAdvancedFilterCount =
    (selectedCategory ? 1 : 0) +
    (selectedSort && selectedSort !== 'recent' ? 1 : 0) +
    (minPrice ? 1 : 0) +
    (maxPrice ? 1 : 0);

  const hasActiveFilters = Boolean(
    query ||
    selectedCategory ||
    selectedLocation ||
    (selectedSort && selectedSort !== 'recent') ||
    minPrice ||
    maxPrice
  );

  return (
    <div className="space-y-4 mb-8">
      {/* Primary search, campus selector, and Filter Modal button */}
      <div className="flex flex-col sm:flex-row items-center gap-3">
        {/* Search bar */}
        <div className="flex-1 w-full">
          <SearchBar
            defaultValue={query || ''}
            onSearch={handleSearch}
            placeholder="Rechercher du matériel, un cours, un campus..."
          />
        </div>

        {/* Campus / Location selector */}
        <div className="relative w-full sm:w-52 shrink-0">
          <div className="absolute left-3.5 top-1/2 -translate-y-1/2 text-slate-400 pointer-events-none">
            <svg
              className="w-4 h-4"
              fill="none"
              stroke="currentColor"
              viewBox="0 0 24 24"
              strokeWidth={2}
            >
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                d="M15 10.5a3 3 0 11-6 0 3 3 0 016 0z"
              />
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                d="M19.5 10.5c0 7.142-7.5 11.25-7.5 11.25S4.5 17.642 4.5 10.5a7.5 7.5 0 1115 0z"
              />
            </svg>
          </div>
          <select
            value={selectedLocation || ''}
            onChange={handleLocationChange}
            className="w-full pl-10 pr-9 py-2.5 bg-slate-50/70 hover:bg-slate-50 focus:bg-white border border-slate-200 rounded-xl text-sm text-slate-800 font-medium focus:outline-hidden focus:border-[#00babc] focus:ring-2 focus:ring-[#00babc]/20 transition-all cursor-pointer appearance-none"
          >
            <option value="">Tous les campus</option>
            {locations.map((loc) => (
              <option key={loc.id} value={loc.id}>
                {loc.location}
              </option>
            ))}
          </select>
          <div className="absolute right-3.5 top-1/2 -translate-y-1/2 text-slate-400 pointer-events-none">
            <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24" strokeWidth={2}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M19.5 8.25l-7.5 7.5-7.5-7.5" />
            </svg>
          </div>
        </div>

        {/* Modal Trigger Button: "Filtres" */}
        <Button
          type="button"
          variant={activeAdvancedFilterCount > 0 ? 'primary' : 'outline'}
          size="md"
          onClick={() => setIsFilterModalOpen(true)}
          className={`w-full sm:w-auto shrink-0 ${activeAdvancedFilterCount > 0 ? '' : 'bg-white'}`}
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
              d="M10.5 6h9.75M10.5 6a1.5 1.5 0 11-3 0m3 0a1.5 1.5 0 10-3 0M3.75 6H7.5m3 12h9.75m-9.75 0a1.5 1.5 0 01-3 0m3 0a1.5 1.5 0 00-3 0m-3.75 0H7.5m9-6h3.75m-3.75 0a1.5 1.5 0 01-3 0m3 0a1.5 1.5 0 00-3 0m-9.75 0h9.75"
            />
          </svg>
          <span>Filtres</span>
          {activeAdvancedFilterCount > 0 && (
            <span className="ml-1 w-5 h-5 rounded-full bg-slate-950 text-white text-[11px] font-bold flex items-center justify-center">
              {activeAdvancedFilterCount}
            </span>
          )}
        </Button>
      </div>

      {/* Status bar: Total count, active category badge and reset filters button */}
      <div className="flex items-center justify-between text-xs text-slate-500 pt-1">
        <div className="flex items-center gap-2 flex-wrap">
          <span>
            <strong className="font-semibold text-slate-900">{totalResults}</strong>{' '}
            {totalResults <= 1 ? 'annonce trouvée' : 'annonces trouvées'}
          </span>
          {selectedCategory && (
            <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-md bg-[#00babc]/10 text-[#008e90] font-semibold text-[11px]">
              {categories.find((c) => c.id === selectedCategory)?.category_name || selectedCategory}
              <button
                type="button"
                onClick={() => router.push(buildUrl({ category: '' }))}
                className="hover:text-slate-900 cursor-pointer ml-0.5"
                title="Supprimer ce filtre"
              >
                ✕
              </button>
            </span>
          )}
        </div>

        {hasActiveFilters && (
          <ResetFiltersButton className="font-semibold text-[#00babc] hover:text-[#008e90] transition-colors flex items-center gap-1">
            <svg className="w-3 h-3" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2.5}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M6 18L18 6M6 6l12 12" />
            </svg>
            Réinitialiser les filtres
          </ResetFiltersButton>
        )}
      </div>

      {/* Modal containing FilterModalContent */}
      <Modal
        isOpen={isFilterModalOpen}
        onClose={() => setIsFilterModalOpen(false)}
        title="Filtres & Tri"
      >
        <FilterModalContent
          categories={categories}
          initialCategory={selectedCategory}
          initialSort={selectedSort}
          initialMinPrice={minPrice}
          initialMaxPrice={maxPrice}
          onApply={(filters) => {
            setIsFilterModalOpen(false);
            router.push(
              buildUrl({
                category: filters.category !== undefined ? filters.category : '',
                sort: filters.sort,
                minPrice: filters.minPrice || '',
                maxPrice: filters.maxPrice || '',
              })
            );
          }}
          onReset={() => {
            setIsFilterModalOpen(false);
            router.push(
              buildUrl({
                category: '',
                sort: 'recent',
                minPrice: '',
                maxPrice: '',
              })
            );
          }}
          onClose={() => setIsFilterModalOpen(false)}
        />
      </Modal>
    </div>
  );
}

export default FilterBar;

