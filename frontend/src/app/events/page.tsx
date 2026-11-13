'use client';
import { useEffect, useState, Suspense } from 'react';
import Link from 'next/link';
import { useSearchParams } from 'next/navigation';
import { isDemoMode, listEvents } from '@/lib/api-client';
import type { Event } from '@/types/api';
import SiteHeader, { useSelectedCity } from '@/components/SiteHeader';
import PixelOrnament from '@/components/PixelOrnament';
import { EventCard } from '@/components/EventCard';
import AgentChatDrawer from '@/components/AgentChatDrawer';
import '../catalog.css';
import '../home.css';
import '../inner.css';

const directions = [
  { name:'Кино', text:'Фильмы, кинотеатры и сеансы', mark:'01', href:'/cinema' },
  { name:'Концерты', text:'Музыка и живые выступления', mark:'02' },
  { name:'Выставки', text:'Искусство и новые открытия', mark:'03' },
  { name:'Мастер-классы', text:'Создавайте и пробуйте', mark:'04' },
  { name:'Театр', text:'Спектакли и постановки', mark:'05' },
  { name:'Спорт', text:'Соревнования и спортивные события', mark:'06' },
  { name:'Экскурсии', text:'Организации и путешествия по республике', mark:'07', href:'/excursions' },
];
function EventsContent() {
  const params = useSearchParams();
  const category = params.get('category') || '';
  const city = useSelectedCity();
  const [items,setItems] = useState<Event[]>([]);
  const [loading,setLoading] = useState(true);
  const [error,setError] = useState(false);
  const [attempt,setAttempt] = useState(0);
  useEffect(() => {
    if (!category) return;
    let active = true;
    setLoading(true); setError(false);
    listEvents({ category, city: city || undefined }).then(result => { if(active) setItems(result.items); }).catch(() => { if(active) setError(true); }).finally(() => { if(active) setLoading(false); });
    return () => { active=false; };
  }, [category,city,attempt]);
  return <main className="hybrid-page"><SiteHeader/><div className="inner-page"><Link className="inner-back" href={category ? '/events' : '/'}>← {category ? 'Все направления' : 'Главная'}</Link><p className="home-kicker">АФИША РЕСПУБЛИКИ</p><h1>{category || 'Направления'}<span>.</span></h1>
    {!category ? <section className="direction-section events-directions" aria-label="Направления афиши"><div className="direction-grid">{directions.map(direction => <Link key={direction.name} className="direction-card" href={direction.href || `/events?category=${encodeURIComponent(direction.name)}`}><div className="direction-art" aria-hidden="true"><PixelOrnament className="direction-ornament"/><span>{direction.mark} / 07</span></div><div className="direction-copy"><small>АФИША БАШКОРТОСТАНА</small><h2>{direction.name}</h2><p>{direction.text}</p><span className="direction-link">Открыть раздел ↗</span></div></Link>)}</div></section> : <section className="category-results" aria-label={`События: ${category}`}>
      {loading ? <div className="catalog-status" role="status">Загружаем события…</div> : error ? <div className="catalog-empty" role="alert"><h2>Не удалось загрузить события</h2><button className="catalog-button catalog-button-secondary" onClick={()=>setAttempt(n=>n+1)}>Повторить</button></div> : items.length ? <div className="home-event-grid">{items.map(event => <EventCard key={event.id} event={event}/>)}</div> : <div className="category-empty"><h2>Пока нет событий</h2><p>В этом разделе ещё нет мероприятий. Попробуйте выбрать другое направление.</p><Link href="/events">Все направления ↗</Link></div>}
    </section>}
  </div><AgentChatDrawer/></main>;
}
export default function EventsPage(){return <Suspense fallback={<p>Загружаем афишу…</p>}><EventsContent/></Suspense>}
