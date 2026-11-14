'use client';

import { useEffect, useState, type FormEvent } from 'react';
import Link from 'next/link';
import AgentChatDrawer from '@/components/AgentChatDrawer';
import SiteHeader, { useSelectedCity } from '@/components/SiteHeader';
import { isDemoMode, listEvents } from '@/lib/api-client';
import type { Event } from '@/types/api';
import './catalog.css';
import './home.css';
import './editorial-home.css';

const sections = [
  { label: 'Все события', href: '/events', symbol: '↗' },
  { label: 'Кино', href: '/cinema', symbol: '◉' },
  { label: 'Экскурсии', href: '/excursions', symbol: '⌁' },
  { label: 'Подборки', href: '/sections', symbol: '✳' },
];

function eventDate(value: string) {
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? 'Дата уточняется' : new Intl.DateTimeFormat('ru-RU', { day: 'numeric', month: 'long', hour: '2-digit', minute: '2-digit', timeZone: 'Asia/Yekaterinburg' }).format(date);
}

function EventStory({ event, featured = false }: { event: Event; featured?: boolean }) {
  return <Link href={`/events/${encodeURIComponent(event.id)}`} className={`editorial-story ${featured ? 'editorial-story-featured' : ''}`}>
    {featured && <div className="editorial-art" aria-hidden="true">{event.image_url ? <img src={event.image_url} alt="" /> : <><span>АФИША / БАШКОРТОСТАН</span><b>✳</b><small>КУЛЬТУРА РЯДОМ</small></>}</div>}
    <div className="editorial-story-copy"><div className="editorial-meta"><span>{eventDate(event.starts_at)}</span><span>{event.category || 'Событие'}</span></div><h3>{event.title}</h3><p>{[event.city, event.venue].filter(Boolean).join(' · ')}</p>{isDemoMode && <small className="editorial-demo">Вымышленное событие · пример</small>}</div><span className="editorial-arrow" aria-hidden="true">↗</span>
  </Link>;
}

export default function HomePage() {
  const city = useSelectedCity();
  const [events, setEvents] = useState<Event[]>([]);
  const [status, setStatus] = useState<'loading' | 'error' | 'ready'>('loading');
  const [retry, setRetry] = useState(0);
  const [question, setQuestion] = useState('');
  const [launchRequest, setLaunchRequest] = useState<{ id: number; text: string }>();

  useEffect(() => {
    let active = true;
    setStatus('loading');
    setEvents([]);
    const dateFrom = new Intl.DateTimeFormat('en-CA', { timeZone: 'Asia/Yekaterinburg', year: 'numeric', month: '2-digit', day: '2-digit' }).format(new Date());
    listEvents({ city: city || undefined, date_from: dateFrom }).then(result => {
      if (!active) return;
      setEvents(result.items.filter(event => {
        const time = new Date(event.starts_at).getTime();
        return Number.isFinite(time) && time >= Date.now() && (!city || event.city.toLocaleLowerCase('ru') === city.toLocaleLowerCase('ru'));
      }).sort((a, b) => new Date(a.starts_at).getTime() - new Date(b.starts_at).getTime()).slice(0, 4));
      setStatus('ready');
    }).catch(() => { if (active) setStatus('error'); });
    return () => { active = false; };
  }, [city, retry]);

  function askAssistant(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setLaunchRequest({ id: Date.now(), text: question.trim() });
  }

  return <main className="hybrid-page editorial-home"><SiteHeader />
    <div className="editorial-wrap">
      <div className="editorial-topline"><span>BASH АФИШ / КУЛЬТУРА БАШКОРТОСТАНА</span><span>{city || 'ВСЕ ГОРОДА'} / КУЛЬТУРА РЯДОМ</span></div>
      <section aria-labelledby="issue-title">
        <div className="editorial-section-heading"><div><span className="editorial-kicker">АФИША / {city || 'БАШКОРТОСТАН'}</span><h1 id="issue-title">Ближайшие события</h1></div><Link href="/events">Вся афиша ↗</Link></div>
        {isDemoMode && <p className="editorial-notice">Демонстрационный режим: события ниже вымышлены и приведены только для примера.</p>}
        {status === 'loading' && <p className="editorial-state" role="status">Загружаем события…</p>}
        {status === 'error' && <div className="editorial-state" role="alert"><p>Не удалось загрузить события. Попробуйте ещё раз.</p><button type="button" onClick={() => setRetry(value => value + 1)}>Повторить ↻</button></div>}
        {status === 'ready' && events.length === 0 && <div className="editorial-state"><p>Ближайших событий {city ? `для города ${city}` : 'пока'} не найдено.</p><Link href="/events">Перейти к афише ↗</Link></div>}
        {status === 'ready' && events.length > 0 && <div className="editorial-grid"><div><EventStory event={events[0]} featured/><p className="editorial-note">ИСКУССТВО И ГОРОД &nbsp; / &nbsp; БЛИЖАЙШИЕ СОБЫТИЯ</p></div><div className="editorial-list"><div className="editorial-list-heading"><span>НА ЗАМЕТКУ</span><span>01 — {String(events.length).padStart(2, '0')}</span></div>{events.slice(1).map(event => <EventStory key={event.id} event={event}/>)}{events.length === 1 && <p className="editorial-list-empty">Больше событий ищите в полной афише.</p>}<Link className="editorial-inline" href="/events">Открыть всю афишу ↗</Link></div></div>}
      </section>
      <section className="editorial-explore" aria-labelledby="explore-title"><div><span className="editorial-kicker">ПРОДОЛЖАЙТЕ ОТКРЫВАТЬ</span><h2 id="explore-title">Больше культуры</h2><p>Выбирайте, как провести свободное время.</p></div><div className="editorial-services">{sections.map(section => <Link href={section.href} key={section.href}><span>{section.symbol}</span><strong>{section.label}</strong><span>↗</span></Link>)}</div></section>
      <section className="editorial-assistant"><div><span className="editorial-kicker">ЕСТЬ ИДЕЯ?</span><h2>Спросите помощника</h2><p>Расскажите, что ищете, и продолжите разговор в чате.</p></div><form onSubmit={askAssistant}><label className="home-sr" htmlFor="editorial-question">Запрос помощнику</label><input id="editorial-question" value={question} onChange={event => setQuestion(event.target.value)} placeholder="Например, концерт для всей семьи"/><button type="submit">Спросить ↗</button></form></section>
    </div><footer className="home-footer"><Link href="/">✳ Bash Афиш</Link><span>Культура начинается здесь.</span><Link href="/widget">Виджет для сайта ↗</Link></footer><AgentChatDrawer launchRequest={launchRequest}/></main>;
}
