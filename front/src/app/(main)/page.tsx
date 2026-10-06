import ListingCard from "@/components/listings/ListingCard";
import FilterBar from "@/components/listings/FilterBar";
import ResetFiltersButton from "@/components/listings/ResetFiltersButton";
import Pagination from "@/components/ui/Pagination";
import { listingsApi } from "@/lib/api/listings";
import { catalogApi } from "@/lib/api/catalog";
import { parseOptionalId, parsePage, parsePrice, parseQuery, parseSort } from "@/lib/listings/filters";
import { Card } from "@/components/ui/Card";
import { logError } from "@/lib/log";
import type { Category, Listing, Location } from "@/types";

interface HomePageProps {
  searchParams?: Promise<{
    q?: string;
    category?: string;
    location?: string;
    sort?: string;
    minPrice?: string;
    maxPrice?: string;
    page?: string;
  }>;
}

export default async function Home({ searchParams }: HomePageProps) {
  const params = await searchParams;
  const currentPageNum = parsePage(params?.page);
  const query = parseQuery(params?.q);
  const categoryNum = parseOptionalId(params?.category);
  const locationNum = parseOptionalId(params?.location);
  const selectedSort = parseSort(params?.sort);
  const minPriceNum = parsePrice(params?.minPrice);
  const maxPriceNum = parsePrice(params?.maxPrice);

  const selectedCategory = categoryNum !== undefined ? String(categoryNum) : "";
  const selectedLocation = locationNum !== undefined ? String(locationNum) : "";
  const minPrice = minPriceNum !== undefined ? String(minPriceNum) : undefined;
  const maxPrice = maxPriceNum !== undefined ? String(maxPriceNum) : undefined;

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

  let listings: Listing[] = [];
  let totalResults = 0;
  let currentPage = 1;
  let totalPages = 1;
  try {
    const result = await listingsApi.getAll({
      page: currentPageNum,
      limit: 30,
      query,
      category: selectedCategory,
      location: selectedLocation,
      sort: selectedSort,
      min_price: minPriceNum,
      max_price: maxPriceNum,
    });
    listings = result.data;
    totalResults = result.total;
    currentPage = result.page;
    totalPages = result.total_pages;
  } catch (err) {
    console.error("Impossible de charger les annonces :", err);
  }

  return (
    <main className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
      {/* Filters Section (replaced static header) */}
      <FilterBar
        categories={categories}
        locations={locations}
        selectedCategory={selectedCategory}
        selectedLocation={selectedLocation}
        selectedSort={selectedSort}
        minPrice={minPrice}
        maxPrice={maxPrice}
        query={query || undefined}
        totalResults={totalResults}
      />

      {/* Listings Grid or Empty State */}
      {listings.length === 0 ? (
        <Card>
          <p className="text-center text-slate-600 font-medium">
            Aucune annonce ne correspond à vos filtres.
          </p>
          <ResetFiltersButton className="mt-3 block text-center text-sm text-[#00babc] hover:underline font-semibold mx-auto">
            Réinitialiser tous les filtres
          </ResetFiltersButton>
        </Card>
      ) : (
        <>
          <section className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
            {listings.map((listing, index) => (
              <ListingCard key={listing.id} data={listing} preload={index < 3} />
            ))}
          </section>

          {totalPages > 1 && (
            <div className="mt-10">
              <Pagination
                currentPage={currentPage}
                totalPages={totalPages}
                totalResults={totalResults}
                limit={30}
                baseParams={{
                  q: query || undefined,
                  category: selectedCategory || undefined,
                  location: selectedLocation || undefined,
                  sort: selectedSort,
                  minPrice,
                  maxPrice,
                }}
              />
            </div>
          )}
        </>
      )}
    </main>
  );
}