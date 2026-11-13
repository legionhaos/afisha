/** Temporary frontend contract; align fields with the backend before integration. */
export interface Event {
  id: string;
  title: string;
  starts_at: string;
  city: string;
  venue: string | null;
  address: string | null;
  description: string | null;
  image_url: string | null;
  min_price: number | null;
  max_price: number | null;
  age_restriction: string | null;
  source_url: string | null;
  category: string | null;
}
export interface EventFilters {
  city?: string;
  category?: string;
  date_from?: string;
  date_to?: string;
  query?: string;
  free?: string;
  page?: number;
}
export interface EventsResponse { items: Event[]; total: number }
