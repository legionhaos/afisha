'use client';

import { useEffect, useState } from 'react';
import { EventCard } from '@/components/EventCard';
import { listEvents } from '@/lib/api-client';
import type { Event, EventFilters } from '@/types/api';
import './widget.css';

export default function WidgetPage() {
  const [items, setItems] = useState<Event[]>([]);
  const [total, setTotal] = useState(0);
  const [status, setStatus] = useState<'loading' | 'ready' | 'error'>('loading');
  const [attempt, setAttempt] = useState(0);

  useEffect(() => {
    let active = true;
    const params = new URLSearchParams(window.location.search);
    const filters: EventFilters = {};
    for (const key of ['city', 'category', 'date_from', 'date_to', 'query', 'free'] as const) {
      const value = params.get(key);
      if (value) filters[key] = value;
    }
    const page = Number(params.get('page'));
    if (Number.isSafeInteger(page) && page > 0) filters.page = page;
    setStatus('loading');
    listEvents(filters).then(result => {
      if (active) { setItems(result.items); setTotal(result.total); setStatus('ready'); }
    }).catch(() => { if (active) setStatus('error'); });
    return () => { active = false; };
  }, [attempt]);

  return <main className="widget-shell">
    <header className="widget-header"><div><span className="widget-kicker">Афиша</span><h1>События рядом</h1></div><a href="/" target="_blank" rel="noreferrer">Вся афиша ↗</a></header>
    {process.env.NEXT_PUBLIC_DATA_MODE !== 'api' && <p className="widget-demo">Демонстрационные данные</p>}
    {status === 'loading' ? <p className="widget-status" role="status">Загружаем события…</p> : status === 'error' ? <div className="widget-status" role="alert"><p>Не удалось загрузить события.</p><button onClick={() => setAttempt(n => n + 1)}>Попробовать снова</button></div> : items.length ? <><p className="widget-count">Найдено: {total}</p><div className="widget-grid">{items.map(event => <EventCard key={event.id} event={event} />)}</div></> : <p className="widget-status">Событий по выбранным условиям не найдено.</p>}
  </main>;
}
