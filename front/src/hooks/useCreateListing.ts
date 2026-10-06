"use client";

import { useState, useRef, useEffect } from "react";
import { useRouter } from "next/navigation";
import { catalogApi } from "@/lib/api/catalog";
import { isObjectCategory } from "@/lib/categories";
import type { Category, Location, ListingCondition } from "@/types";

export const CONDITIONS: {
  value: ListingCondition;
  label: string;
}[] = [
  {
    value: 'new',
    label: 'Neuf (jamais utilisé)',
  },
  {
    value: 'like_new',
    label: 'Très bon état (comme neuf)',
  },
  {
    value: 'good',
    label: 'Bon état (fonctionnel)',
  },
  {
    value: 'fair',
    label: 'État correct',
  },
  {
    value: 'for_parts',
    label: 'Pour pièces / Réparation',
  },
];

export function useCreateListing() {
  const router = useRouter();
  const formRef = useRef<HTMLFormElement>(null);
  const [categories, setCategories] = useState<Category[]>([]);
  const [locations, setLocations] = useState<Location[]>([]);
  const [selectedCategoryId, setSelectedCategoryId] = useState<string>('');
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [isCancelModalOpen, setIsCancelModalOpen] = useState(false);

  useEffect(() => {
    let cancelled = false;
    Promise.all([
      catalogApi.getCategories(),
      catalogApi.getLocations(),
    ])
      .then(([cats, locs]) => {
        if (cancelled) return;
        setCategories(cats);
        setLocations(locs);
        setSelectedCategoryId(cats[0]?.id ?? 'cat-objet');
      })
      .catch((err: unknown) => {
        if (!cancelled) {
          setError(err instanceof Error ? err.message : 'Impossible de charger le catalogue');
        }
      })
      .finally(() => {
        if (!cancelled) setIsLoading(false);
      });
    return () => { cancelled = true; };
  }, []);

  const selectedCat = categories.find((c) => String(c.id) === String(selectedCategoryId));
  const isObject = isObjectCategory(selectedCat ?? selectedCategoryId, categories);

  /**
   * Check whether the user has entered data in the form.
   */
  const hasFormInputs = (): boolean => {
    if (!formRef.current) return false;
    const formData = new FormData(formRef.current);

    const title = (formData.get('title') as string)?.trim();
    const price = (formData.get('price') as string)?.trim();
    const body = (formData.get('body') as string)?.trim();
    const imageData = (formData.get('image_data') as string)?.trim();
    const categoryId = formData.get('category_id') as string;
    const locationId = formData.get('location_id') as string;

    // Text fields or image filled
    if (title || price || body || imageData) {
      return true;
    }

    // Category or location changed from the initial values
    if (categoryId && categoryId !== categories[0]?.id) {
      return true;
    }
    if (locationId && locationId !== locations[0]?.id) {
      return true;
    }

    return false;
  };

  const handleCancel = () => {
    if (hasFormInputs()) {
      setIsCancelModalOpen(true);
    } else {
      router.push('/');
    }
  };

  const handleBackLink = (e: React.MouseEvent) => {
    if (hasFormInputs()) {
      e.preventDefault();
      setIsCancelModalOpen(true);
    }
  };

  return {
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
  };
}
