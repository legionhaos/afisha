'use client';

import { useEffect, useState } from 'react';
import Link from 'next/link';
import { useParams } from 'next/navigation';
import { getEvent, isDemoMode } from '@/lib/api-client';
import type { Event } from '@/types/api';
import AgentChatDrawer from '@/components/AgentChatDrawer';
import { formatEventDate, formatEventPrice } from '@/components/EventCard';
import '../../catalog.css';

export default function EventDetailPage() {
  const params = useParams<{ id: string }>();
  const [event, setEvent] = useState<Event | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(false);
  const [attempt, setAttempt] = useState(0);
  useEffect(() => {
    let active = true;
    setLoading(true); setError(false); setEvent(null);
    getEvent(params.id).then(result => { if (active) setEvent(result); }).catch(() => { if (active) setError(true); }).finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, [params.id, attempt]);
  return <main className="catalog-shell"><header className="catalog-header"><Link className="catalog-logo" href="/">афиша<span>.</span></Link><span>События рядом и не только</span></header>
    <div className="detail-wrap"><Link className="back-link" href="/events">← Все события</Link>
      {loading ? <div className="catalog-status" role="status">Загружаем событие…</div> : error || !event ? <div className="catalog-empty" role="alert"><h1>Не удалось загрузить событие</h1><p>Возможно, оно недоступно или возникла ошибка соединения.</p><button className="catalog-button catalog-button-secondary" onClick={() => setAttempt(n => n + 1)}>Повторить</button></div> : <article className="event-detail">
        <div className="detail-image">{event.image_url ? <img src={event.image_url} alt="" /> : <span aria-hidden="true">✦</span>}</div>
        <div className="detail-main"><div className="detail-copy"><p className="catalog-eyebrow">{event.category || 'Событие'}</p><h1>{event.title}</h1>{event.description && <><h2>О событии</h2><p className="detail-description">{event.description}</p></>}</div>
          <aside className="detail-info" aria-label="Информация о событии"><div><small>Дата и время</small><time dateTime={event.starts_at}>{formatEventDate(event.starts_at)}</time></div><div><small>Место</small><span>{[event.city, event.venue, event.address].filter(Boolean).join(', ')}</span></div><div><small>Стоимость</small><span>{formatEventPrice(event.min_price, event.max_price)}</span></div>{event.age_restriction && <div><small>Возраст</small><span>{event.age_restriction}</span></div>}{event.source_url && <a className="catalog-button detail-source" href={event.source_url} target="_blank" rel="noopener noreferrer">Подробнее на сайте ↗</a>}</aside>
        </div></article>}
    </div><AgentChatDrawer /></main>;
}
