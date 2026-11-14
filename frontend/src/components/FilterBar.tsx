'use client';

import { useEffect, useState, type FormEvent } from 'react';
import type { EventFilters } from '@/types/api';

type Props = { filters: EventFilters; onChange: (filters: EventFilters) => void };

export function FilterBar({ filters, onChange }: Props) {
  const [draft, setDraft] = useState<EventFilters>(filters);
  useEffect(() => setDraft(filters), [filters]);
  const set = (key: keyof EventFilters, value: string) => setDraft(current => ({ ...current, [key]: value || undefined }));
  const submit = (event: FormEvent) => {
    event.preventDefault();
    onChange({ ...draft, page: undefined });
  };
  return (
    <form className="filter-bar" onSubmit={submit} aria-label="Фильтры событий">
      <label className="filter-field filter-search">Поиск<input value={draft.query ?? ''} onChange={e => set('query', e.target.value)} placeholder="Название или ключевое слово" /></label>
      <label className="filter-field">Город<input value={draft.city ?? ''} onChange={e => set('city', e.target.value)} placeholder="Любой город" /></label>
      <label className="filter-field">Категория<input value={draft.category ?? ''} onChange={e => set('category', e.target.value)} placeholder="Все категории" /></label>
      <label className="filter-field">Дата от<input type="date" value={draft.date_from ?? ''} onChange={e => set('date_from', e.target.value)} /></label>
      <label className="filter-field">Дата до<input type="date" value={draft.date_to ?? ''} onChange={e => set('date_to', e.target.value)} /></label>
      <label className="filter-checkbox"><input type="checkbox" checked={draft.free === 'true'} onChange={e => set('free', e.target.checked ? 'true' : '')} /> Бесплатно</label>
      <div className="filter-actions"><button className="catalog-button" type="submit">Найти</button><button className="catalog-button catalog-button-secondary" type="button" onClick={() => { setDraft({}); onChange({}); }}>Сбросить</button></div>
    </form>
  );
}
export default FilterBar;
