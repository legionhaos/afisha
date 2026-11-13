'use client';

import { useEffect, useState } from 'react';
import { isDemoMode, listEvents } from '@/lib/api-client';
import type { Event, EventFilters } from '@/types/api';
import { FilterBar } from '@/components/FilterBar';
import { EventCard } from '@/components/EventCard';
import { EmptyStateDiagnostic } from '@/components/EmptyStateDiagnostic';
import AgentChatDrawer from '@/components/AgentChatDrawer';
import PixelOrnament from '@/components/PixelOrnament';
import './catalog.css';

export default function CatalogPage() {
  const [filters, setFilters] = useState<EventFilters>({});
  const [items, setItems] = useState<Event[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(false);
  const [attempt, setAttempt] = useState(0);
  useEffect(() => {
    let active = true;
    setLoading(true); setError(false);
    listEvents(filters).then(result => { if (active) { setItems(result.items); setTotal(result.total); } }).catch(() => { if (active) setError(true); }).finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, [filters, attempt]);
  return <main className="catalog-shell">
    <header className="catalog-header"><a className="catalog-logo" href="/" aria-label="Афиша Башкортостана — на главную"><span className="logo-mark" aria-hidden="true">✳</span><span className="logo-text">афиша<small>БАШКОРТОСТАН</small></span></a><nav className="header-nav" aria-label="Основная навигация"><a href="#events">События</a><a href="/widget">Виджет</a></nav><span className="header-location">Республика Башкортостан ↗</span></header>
    <section className="catalog-hero"><div className="hero-copy"><p className="catalog-eyebrow"><span className="eyebrow-dot" /> АФИША РЕСПУБЛИКИ БАШКОРТОСТАН</p><h1>Культура<br /><em>рядом</em><span className="hero-period">.</span></h1><p className="hero-description">Открывайте выставки, концерты, спектакли и другие события в городах и районах Башкортостана.</p><a className="hero-link" href="#events">Найти событие <span aria-hidden="true">↗</span></a></div><div className="hero-art" aria-hidden="true"><span className="art-label art-label-top">КУЛЬТУРА / БАШКОРТОСТАН</span><PixelOrnament className="hero-ornament" /><span className="art-label art-label-bottom">ТРАДИЦИИ В НОВОМ РИТМЕ<br />ВПЕЧАТЛЕНИЯ РЯДОМ</span><span className="art-index">02 / 06</span></div></section>
    <section id="events" className="catalog-content" aria-label="Каталог событий">
      {isDemoMode && <div className="demo-notice" role="status"><strong>Демонстрационный режим.</strong> Все события вымышлены. Реальная афиша и ИИ-агент ещё не подключены.</div>}
      <div className="search-intro"><div><p className="catalog-eyebrow">ВАШИ ПЛАНЫ НАЧИНАЮТСЯ ЗДЕСЬ</p><h2>Найдите своё событие</h2></div><p>Выберите то, что подходит именно вам.</p></div>
      <FilterBar filters={filters} onChange={setFilters} />
      <div className="catalog-section-heading"><div><p className="catalog-eyebrow">ОТКРЫВАЙТЕ НОВОЕ</p><h2>Афиша событий<span className="heading-dot">.</span></h2></div>{!loading && !error && <span>Найдено: {total}</span>}</div>
      {loading ? <div className="catalog-status" role="status">Загружаем события…</div> : error ? <div className="catalog-empty" role="alert"><h2>Не удалось загрузить события</h2><p>Проверьте соединение и попробуйте ещё раз.</p><button className="catalog-button catalog-button-secondary" onClick={() => setAttempt(n => n + 1)}>Повторить</button></div> : items.length ? <div className="event-grid">{items.map(event => <EventCard key={event.id} event={event} />)}</div> : <EmptyStateDiagnostic filters={filters} onReset={() => setFilters({})} />}
    </section>
    <footer className="catalog-footer"><div><a className="footer-logo" href="/">✳ афиша<span>.</span></a><p>Культура, которая рядом.</p></div><p>Республика Башкортостан<br />Создано для новых впечатлений</p></footer>
    <AgentChatDrawer />
  </main>;
}
