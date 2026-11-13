import type { Event, EventFilters, EventsResponse } from '@/types/api';

// All examples are fictional and must never be presented as real events.
const demoEvents: Event[] = [
  { id: 'demo-1', title: 'Выставка «Цвета Башкортостана»', starts_at: '2027-06-12T14:00:00+05:00', city: 'Уфа', venue: 'Демонстрационный выставочный зал', address: null, description: 'Пример карточки выставки. Это вымышленное мероприятие для демонстрации интерфейса.', image_url: null, min_price: 0, max_price: 0, age_restriction: '6+', source_url: null, category: 'Выставки' },
  { id: 'demo-2', title: 'Вечер башкирской музыки', starts_at: '2027-06-13T18:00:00+05:00', city: 'Уфа', venue: 'Демонстрационная сцена', address: null, description: 'Вымышленный концерт для демонстрации интерфейса.', image_url: null, min_price: 500, max_price: 900, age_restriction: '12+', source_url: null, category: 'Концерты' },
  { id: 'demo-3', title: 'Семейный спектакль «Легенда гор»', starts_at: '2027-06-19T12:00:00+05:00', city: 'Стерлитамак', venue: 'Демонстрационный театр', address: null, description: 'Вымышленный спектакль для демонстрации интерфейса.', image_url: null, min_price: 350, max_price: 600, age_restriction: '6+', source_url: null, category: 'Театр' },
  { id: 'demo-4', title: 'Мастерская народных ремёсел', starts_at: '2027-06-20T11:00:00+05:00', city: 'Уфа', venue: 'Демонстрационный культурный центр', address: null, description: 'Вымышленный мастер-класс для демонстрации интерфейса.', image_url: null, min_price: 0, max_price: 0, age_restriction: '0+', source_url: null, category: 'Мастер-классы' }
];
export const isDemoMode = process.env.NEXT_PUBLIC_DATA_MODE !== 'api';
type BackendEvent = { id: string; title: string; date_start: string; city: string; venue: string | null; address: string | null; description: string | null; price_min: number | null; price_max: number | null; is_free: boolean; age_limit: number | null; source_url: string | null; category: string | null };
function fromBackend(event: BackendEvent): Event {
  const labels: Record<string, string> = { concert: 'Концерты', theater: 'Театр', exhibition: 'Выставки', festival: 'Фестивали', cinema: 'Кино', excursion: 'Экскурсии', other: 'Другое' };
  return { id: event.id, title: event.title, starts_at: event.date_start, city: event.city, venue: event.venue, address: event.address, description: event.description, image_url: null, min_price: event.is_free ? 0 : event.price_min, max_price: event.is_free ? 0 : event.price_max, age_restriction: event.age_limit == null ? null : `${event.age_limit}+`, source_url: event.source_url?.includes('example.org/demo') ? null : event.source_url, category: event.category ? labels[event.category] || event.category : null };
}

async function getJson<T>(url: string): Promise<T> {
  const response = await fetch(url, { cache: 'no-store' });
  if (!response.ok) throw new Error(response.status === 404 ? 'Мероприятие не найдено' : `Ошибка сервера (${response.status})`);
  return response.json() as Promise<T>;
}
export async function listEvents(filters: EventFilters = {}): Promise<EventsResponse> {
  if (isDemoMode) {
    const items = demoEvents.filter(event => {
      const includes = (a: string | null, b?: string) => !b || (a || '').toLocaleLowerCase('ru').includes(b.toLocaleLowerCase('ru'));
      return includes(event.city, filters.city) && includes(event.category, filters.category) && includes(`${event.title} ${event.description || ''}`, filters.query)
        && (!filters.date_from || event.starts_at.slice(0, 10) >= filters.date_from)
        && (!filters.date_to || event.starts_at.slice(0, 10) <= filters.date_to)
        && (filters.free !== 'true' || event.min_price === 0);
    });
    const page = Math.max(1, filters.page || 1);
    return { items: items.slice((page - 1) * 12, page * 12), total: items.length };
  }
  const params = new URLSearchParams();
  Object.entries(filters).forEach(([key, value]) => { if (value !== undefined && value !== '') params.set(key, String(value)); });
  const categoryMap: Record<string, string> = { 'Концерты': 'concert', 'Театр': 'theater', 'Выставки': 'exhibition', 'Кино': 'cinema', 'Экскурсии': 'excursion' };
  if (filters.category) {
    const category = categoryMap[filters.category];
    if (!category) return { items: [], total: 0 };
    params.set('category', category);
  }
  if (filters.query) { params.delete('query'); params.set('query_text', filters.query); }
  if (filters.free) { params.delete('free'); params.set('is_free', filters.free); }
  const response = await getJson<{ items: BackendEvent[]; total: number }>(`/api/v1/events?${params}`);
  return { items: response.items.map(fromBackend), total: response.total };
}
export async function getEvent(id: string): Promise<Event> {
  if (isDemoMode) {
    const event = demoEvents.find(item => item.id === id);
    if (!event) throw new Error('Мероприятие не найдено');
    return event;
  }
  return fromBackend(await getJson<BackendEvent>(`/api/v1/events/${encodeURIComponent(id)}`));
}
