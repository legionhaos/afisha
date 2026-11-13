import Link from 'next/link';
import type { Event } from '@/types/api';

export function formatEventDate(value: string) {
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? value : new Intl.DateTimeFormat('ru-RU', { day: 'numeric', month: 'long', year: 'numeric', hour: '2-digit', minute: '2-digit', timeZone: 'Asia/Yekaterinburg' }).format(date);
}
export function formatEventPrice(min: number | null, max: number | null) {
  if (min == null && max == null) return 'Цена не указана';
  if (min === 0 && (max == null || max === 0)) return 'Бесплатно';
  const money = (value: number) => `${new Intl.NumberFormat('ru-RU').format(value)} ₽`;
  if (min != null && max != null) return min === max ? money(min) : `${money(min)} — ${money(max)}`;
  return min != null ? `от ${money(min)}` : `до ${money(max!)}`;
}
export function EventCard({ event }: { event: Event }) {
  return <Link className="event-card" href={`/events/${encodeURIComponent(event.id)}`}>
    <div className="event-card-image">{event.image_url ? <img src={event.image_url} alt="" loading="lazy" /> : <span className="card-art" aria-hidden="true">✳</span>}</div>
    <div className="event-card-body">
      <div className="event-card-meta">{event.category && <span>{event.category}</span>}<time dateTime={event.starts_at}>{formatEventDate(event.starts_at)}</time></div>
      <h2>{event.title}</h2>
      <p className="event-card-location">{[event.city, event.venue].filter(Boolean).join(' · ')}</p>
      <div className="event-card-bottom"><strong>{formatEventPrice(event.min_price, event.max_price)}</strong><span className="card-bottom-right">{event.age_restriction && <span>{event.age_restriction}</span>}<span className="card-arrow" aria-hidden="true">↗</span></span></div>
    </div>
  </Link>;
}
export default EventCard;
