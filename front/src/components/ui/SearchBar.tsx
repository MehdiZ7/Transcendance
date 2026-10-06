'use client';

import { MAX_SEARCH_LENGTH } from "@/lib/limits";
import React, { useState } from 'react';
import { useRouter } from 'next/navigation';

export interface SearchBarProps
  extends Omit<React.InputHTMLAttributes<HTMLInputElement>, 'onChange' | 'onSubmit'> {
  value?: string;
  defaultValue?: string;
  onChange?: (value: string) => void;
  onSearch?: (value: string) => void;
  placeholder?: string;
  className?: string;
  name?: string;
}

export function SearchBar({
  value: controlledValue,
  defaultValue = '',
  onChange,
  onSearch,
  placeholder = 'Search...',
  className = '',
  name = 'q',
  ...rest
}: SearchBarProps) {
  const router = useRouter();
  const [internalValue, setInternalValue] = useState(defaultValue);
  const isControlled = controlledValue !== undefined;
  const query = isControlled ? controlledValue : internalValue;

  // Sync internal state during render if defaultValue prop updates
  const [prevDefaultValue, setPrevDefaultValue] = useState(defaultValue);
  if (!isControlled && defaultValue !== prevDefaultValue) {
    setPrevDefaultValue(defaultValue);
    setInternalValue(defaultValue);
  }

  const handleChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const nextVal = e.target.value;
    if (!isControlled) {
      setInternalValue(nextVal);
    }
    onChange?.(nextVal);
  };

  const handleClear = () => {
    if (!isControlled) {
      setInternalValue('');
    }
    onChange?.('');
    if (onSearch) {
      onSearch('');
    } else {
      router.push('/');
    }
  };

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (onSearch) {
      onSearch(query);
    } else {
      const trimmed = query.trim();
      router.push(trimmed ? `/?${name}=${encodeURIComponent(trimmed)}` : '/');
    }
  };

  return (
    <form onSubmit={handleSubmit} className={`relative flex items-center w-full ${className}`}>
      {/* Search icon */}
      <div className="absolute left-3.5 text-slate-400 pointer-events-none">
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
            d="M21 21l-5.197-5.197m0 0A7.5 7.5 0 105.196 5.196a7.5 7.5 0 0010.607 10.607z"
          />
        </svg>
      </div>

      {/* Input field */}
      <input
        type="text"
        name={name}
        value={query}
        onChange={handleChange}
        placeholder={placeholder}
        maxLength={MAX_SEARCH_LENGTH}
        className="w-full pl-10 pr-10 py-2.5 text-sm bg-slate-50/70 hover:bg-slate-50 focus:bg-white border border-slate-200 rounded-xl text-slate-900 placeholder:text-slate-400 focus:outline-hidden focus:border-[#00babc] focus:ring-2 focus:ring-[#00babc]/20 transition-all"
        {...rest}
      />

      {/* Clear button */}
      {query && (
        <button
          type="button"
          onClick={handleClear}
          className="absolute right-3 p-1 rounded-full text-slate-400 hover:text-slate-600 hover:bg-slate-200/60 transition-colors cursor-pointer"
          aria-label="Clear search"
        >
          <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24" strokeWidth={2}>
            <path strokeLinecap="round" strokeLinejoin="round" d="M6 18L18 6M6 6l12 12" />
          </svg>
        </button>
      )}
    </form>
  );
}

export default SearchBar;
