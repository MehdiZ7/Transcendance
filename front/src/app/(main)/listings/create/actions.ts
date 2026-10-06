'use server';

import { revalidatePath } from 'next/cache';
import { redirect } from 'next/navigation';
import { listingsApi } from '@/lib/api/listings';
import { catalogApi } from '@/lib/api/catalog';
import { getDefaultImageForCategory } from '@/lib/images';
import { isObjectCategory } from '@/lib/categories';
import { logError } from '@/lib/log';
import type { ListingCondition, Category, Location } from '@/types';

export interface CreateListingState {
  error?: string | null;
}

export async function createListingAction(
  _prevState: CreateListingState,
  formData: FormData
): Promise<CreateListingState> {
  const title = (formData.get('title') as string) || '';
  const price = Number(formData.get('price')) || 0;
  let categories: Category[] = [];
  let locations: Location[] = [];
  try {
    [categories, locations] = await Promise.all([
      catalogApi.getCategories(),
      catalogApi.getLocations(),
    ]);
  } catch (err) {
    logError('Impossible de charger le catalogue :', err);
  }
  const category_id = (formData.get('category_id') as string) || categories[0]?.id;
  const location_id = (formData.get('location_id') as string) || locations[0]?.id;
  const isObject = isObjectCategory(category_id, categories);
  const condition = isObject
    ? ((formData.get('condition') as ListingCondition) || 'good')
    : undefined;
  const body = (formData.get('body') as string) || '';
  const imageData =
    ((formData.get('image_data') as string) || '').trim() ||
    ((formData.get('image_url') as string) || '').trim();

  // Use the uploaded image's path, or assign a styled category SVG placeholder
  const finalImageUrl = imageData || getDefaultImageForCategory(category_id);

  let redirectUrl: string | null = null;
  try {
    const newListing = await listingsApi.create({
      title,
      price,
      category_id,
      location_id,
      condition,
      body,
      image_urls: [finalImageUrl],
    });

    revalidatePath('/');
    redirectUrl = `/listings/${newListing.public_id}`;
  } catch (err) {
    logError("Erreur lors de la création de l'annonce :", err);
    return {
      error:
        err instanceof Error
          ? err.message
          : "Une erreur est survenue lors de la publication de l'annonce.",
    };
  }

  if (redirectUrl) {
    redirect(redirectUrl);
  }

  return { error: null };
}
