import type { EventFilters } from '@/types/api';

export function EmptyStateDiagnostic({ filters, onReset }: { filters: EventFilters; onReset: () => void }) {
  const hasFilters = Boolean(filters.query || filters.city || filters.category || filters.date_from || filters.date_to || filters.free);
  return <div className="catalog-empty" role="status"><span className="empty-icon" aria-hidden="true">⌕</span><h2>События не найдены</h2><p>{hasFilters ? 'Попробуйте изменить запрос или убрать некоторые фильтры.' : 'Пока здесь нет событий. Загляните позже.'}</p>{hasFilters && <button className="catalog-button catalog-button-secondary" type="button" onClick={onReset}>Сбросить фильтры</button>}</div>;
}
export default EmptyStateDiagnostic;
