'use client';

import { useEffect, useState, useMemo } from 'react';
import './miniapp.css';

interface EventItem {
  id: string;
  title: string;
  date_start: string;
  city: string;
  venue: string;
  address: string;
  price_min: number;
  price_max: number;
  is_free: boolean;
  age_limit: number;
  category: string;
  description: string;
  image_url: string | null;
  org_link: string | null;
  source_url: string;
  status: string;
}

const CITIES = ['Все', 'Уфа', 'Стерлитамак', 'Салават', 'Нефтекамск', 'Октябрьский', 'Ишимбай', 'Белорецк'];
const CATEGORIES = [
  { label: 'Все', value: '' },
  { label: 'Театр', value: 'theater' },
  { label: 'Концерты', value: 'concert' },
  { label: 'Выставки', value: 'exhibition' },
  { label: 'Фестивали', value: 'festival' },
  { label: 'Шоу', value: 'other' },
];

declare global {
  interface Window {
    Telegram?: {
      WebApp?: {
        ready: () => void;
        expand: () => void;
        close: () => void;
        setHeaderColor?: (color: string) => void;
        setBackgroundColor?: (color: string) => void;
        HapticFeedback?: {
          impactOccurred: (style: 'light' | 'medium' | 'heavy' | 'rigid' | 'soft') => void;
          notificationOccurred: (type: 'error' | 'success' | 'warning') => void;
        };
      };
    };
  }
}

function formatDate(isoStr: string) {
  try {
    const d = new Date(isoStr);
    return new Intl.DateTimeFormat('ru-RU', {
      day: 'numeric',
      month: 'short',
      hour: '2-digit',
      minute: '2-digit',
      timeZone: 'Asia/Yekaterinburg',
    }).format(d);
  } catch {
    return isoStr;
  }
}

function formatPrice(isFree: boolean, min: number, max: number) {
  if (isFree) return 'Бесплатно';
  if (!min && !max) return 'Цена не указана';
  if (min === max) return `${min.toLocaleString('ru-RU')} ₽`;
  if (!min) return `до ${max.toLocaleString('ru-RU')} ₽`;
  if (!max) return `от ${min.toLocaleString('ru-RU')} ₽`;
  return `${min.toLocaleString('ru-RU')} — ${max.toLocaleString('ru-RU')} ₽`;
}

export default function MiniAppPage() {
  const [events, setEvents] = useState<EventItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [selectedCity, setSelectedCity] = useState('Все');
  const [selectedCategory, setSelectedCategory] = useState('');
  const [isFreeOnly, setIsFreeOnly] = useState(false);
  const [searchQuery, setSearchQuery] = useState('');
  const [activeModalEvent, setActiveModalEvent] = useState<EventItem | null>(null);

  // Инициализация Telegram WebApp SDK
  useEffect(() => {
    if (typeof window !== 'undefined' && window.Telegram?.WebApp) {
      const tg = window.Telegram.WebApp;
      tg.ready();
      tg.expand();
      tg.setHeaderColor?.('#09090B');
      tg.setBackgroundColor?.('#09090B');
    }
  }, []);

  // Тактильный отклик (Haptics)
  const triggerHaptic = (style: 'light' | 'medium' = 'light') => {
    if (typeof window !== 'undefined' && window.Telegram?.WebApp?.HapticFeedback) {
      window.Telegram.WebApp.HapticFeedback.impactOccurred(style);
    }
  };

  // Загрузка событий из Backend API
  useEffect(() => {
    let isMounted = true;
    async function loadEvents() {
      setLoading(true);
      try {
        const params = new URLSearchParams({ page_size: '50' });
        if (selectedCity !== 'Все') params.set('city', selectedCity);
        if (selectedCategory) params.set('category', selectedCategory);
        if (isFreeOnly) params.set('is_free', 'true');
        if (searchQuery.trim()) params.set('query_text', searchQuery.trim());

        const res = await fetch(`/api/v1/events?${params.toString()}`);
        if (!res.ok) throw new Error('Failed to load events');
        const data = await res.json();
        if (isMounted) {
          setEvents(data.items || []);
        }
      } catch (err) {
        console.error('Error fetching events:', err);
      } finally {
        if (isMounted) setLoading(false);
      }
    }
    loadEvents();
    return () => {
      isMounted = false;
    };
  }, [selectedCity, selectedCategory, isFreeOnly, searchQuery]);

  return (
    <div className="miniapp-root">
      {/* Sticky Header with Search & Branding */}
      <header className="miniapp-header">
        <div className="miniapp-topline">
          <div className="miniapp-branding">
            <div className="miniapp-badge">
              <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                <path d="M2 10s3-3 3-8 4-1 4-1 4 4 4 9-3 8-3 8" />
                <path d="M22 10s-3-3-3-8-4-1-4-1-4 4-4 9 3 8 3 8" />
              </svg>
            </div>
            <div className="miniapp-title-box">
              <h1>Афиша Башкортостана</h1>
              <p>Культурные события республики</p>
            </div>
          </div>
          <span className="miniapp-stats-pill">{loading ? '…' : `${events.length} соб.`}</span>
        </div>

        {/* Search Input */}
        <div className="miniapp-search-box">
          <svg className="miniapp-search-icon" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
            <circle cx="11" cy="11" r="8" />
            <path d="m21 21-4.3-4.3" />
          </svg>
          <input
            type="text"
            className="miniapp-search-input"
            placeholder="Поиск по названию или площадке…"
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
          />
          {searchQuery && (
            <button
              className="miniapp-search-clear"
              onClick={() => {
                setSearchQuery('');
                triggerHaptic();
              }}
            >
              ✕
            </button>
          )}
        </div>

        {/* Horizontal Cities Filter */}
        <div className="miniapp-scroll-row">
          {CITIES.map((city) => (
            <button
              key={city}
              className={`miniapp-chip ${selectedCity === city ? 'active' : ''}`}
              onClick={() => {
                setSelectedCity(city);
                triggerHaptic();
              }}
            >
              {city}
            </button>
          ))}
        </div>

        {/* Horizontal Categories Filter */}
        <div className="miniapp-scroll-row">
          {CATEGORIES.map((cat) => (
            <button
              key={cat.label}
              className={`miniapp-chip ${selectedCategory === cat.value ? 'active' : ''}`}
              onClick={() => {
                setSelectedCategory(cat.value);
                triggerHaptic();
              }}
            >
              {cat.label}
            </button>
          ))}
          <button
            className={`miniapp-chip ${isFreeOnly ? 'active' : ''}`}
            onClick={() => {
              setIsFreeOnly(!isFreeOnly);
              triggerHaptic();
            }}
          >
            Бесплатно
          </button>
        </div>
      </header>

      {/* Main Content / Event Cards */}
      <main className="miniapp-content">
        {loading ? (
          <div className="miniapp-empty">
            <p>Загрузка афиши…</p>
          </div>
        ) : events.length === 0 ? (
          <div className="miniapp-empty">
            <h3>Событий не найдено</h3>
            <p>Попробуйте сбросить фильтры или выбрать другой город</p>
          </div>
        ) : (
          events.map((ev) => (
            <article
              key={ev.id}
              className="miniapp-card"
              onClick={() => {
                setActiveModalEvent(ev);
                triggerHaptic('medium');
              }}
            >
              <div className="miniapp-card-media">
                {ev.image_url ? (
                  <img src={ev.image_url} alt={ev.title} className="miniapp-card-img" loading="lazy" />
                ) : (
                  <div className="miniapp-card-placeholder">
                    <svg width="36" height="36" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5">
                      <rect width="18" height="18" x="3" y="3" rx="2" ry="2" />
                      <circle cx="9" cy="9" r="2" />
                      <path d="m21 15-3.086-3.086a2 2 0 0 0-2.828 0L6 21" />
                    </svg>
                  </div>
                )}
                <div className="miniapp-card-badges">
                  <span className="miniapp-cat-badge">{ev.category || 'Событие'}</span>
                  {ev.age_limit > 0 && <span className="miniapp-age-badge">{ev.age_limit}+</span>}
                </div>
              </div>

              <div className="miniapp-card-body">
                <h2 className="miniapp-card-title">{ev.title}</h2>
                <div className="miniapp-card-meta">
                  <div className="miniapp-card-row">
                    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                      <rect width="18" height="18" x="3" y="4" rx="2" ry="2" />
                      <line x1="16" x2="16" y1="2" y2="6" />
                      <line x1="8" x2="8" y1="2" y2="6" />
                      <line x1="3" x2="21" y1="10" y2="10" />
                    </svg>
                    <time>{formatDate(ev.date_start)}</time>
                  </div>
                  <div className="miniapp-card-row">
                    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                      <path d="M20 10c0 6-8 12-8 12s-8-6-8-12a8 8 0 0 1 16 0Z" />
                      <circle cx="12" cy="10" r="3" />
                    </svg>
                    <span>
                      {ev.city} · {ev.venue}
                    </span>
                  </div>
                </div>

                <div className="miniapp-card-footer">
                  <span className={`miniapp-price ${ev.is_free ? 'free' : ''}`}>
                    {formatPrice(ev.is_free, ev.price_min, ev.price_max)}
                  </span>
                  <span className="miniapp-action-hint">
                    Подробнее
                    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                      <path d="m9 18 6-6-6-6" />
                    </svg>
                  </span>
                </div>
              </div>
            </article>
          ))
        )}
      </main>

      {/* Modal Detail Sheet */}
      {activeModalEvent && (
        <div
          className="miniapp-modal-overlay"
          onClick={() => {
            setActiveModalEvent(null);
            triggerHaptic();
          }}
        >
          <div className="miniapp-sheet" onClick={(e) => e.stopPropagation()}>
            <div className="miniapp-sheet-handle" />
            <div className="miniapp-sheet-content">
              <div className="miniapp-sheet-header">
                <div>
                  <span className="miniapp-cat-badge">{activeModalEvent.category}</span>
                  <h2 className="miniapp-sheet-title" style={{ marginTop: '6px' }}>
                    {activeModalEvent.title}
                  </h2>
                </div>
                <button
                  className="miniapp-sheet-close"
                  onClick={() => {
                    setActiveModalEvent(null);
                    triggerHaptic();
                  }}
                >
                  ✕
                </button>
              </div>

              <div className="miniapp-card-meta">
                <div className="miniapp-card-row">
                  <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                    <rect width="18" height="18" x="3" y="4" rx="2" ry="2" />
                    <line x1="16" x2="16" y1="2" y2="6" />
                    <line x1="8" x2="8" y1="2" y2="6" />
                    <line x1="3" x2="21" y1="10" y2="10" />
                  </svg>
                  <strong>{formatDate(activeModalEvent.date_start)}</strong>
                </div>
                <div className="miniapp-card-row">
                  <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                    <path d="M20 10c0 6-8 12-8 12s-8-6-8-12a8 8 0 0 1 16 0Z" />
                    <circle cx="12" cy="10" r="3" />
                  </svg>
                  <span>
                    {activeModalEvent.city}, {activeModalEvent.venue}
                  </span>
                </div>
                {activeModalEvent.address && (
                  <div className="miniapp-card-row" style={{ fontSize: '12px', color: '#71717a' }}>
                    <span>Адрес: {activeModalEvent.address}</span>
                  </div>
                )}
                <div className="miniapp-card-row">
                  <span className={`miniapp-price ${activeModalEvent.is_free ? 'free' : ''}`} style={{ fontSize: '16px' }}>
                    {formatPrice(activeModalEvent.is_free, activeModalEvent.price_min, activeModalEvent.price_max)}
                  </span>
                  {activeModalEvent.age_limit > 0 && <span>· Возраст {activeModalEvent.age_limit}+</span>}
                </div>
              </div>

              {activeModalEvent.description && (
                <p className="miniapp-sheet-desc">{activeModalEvent.description}</p>
              )}

              {(activeModalEvent.org_link || activeModalEvent.source_url) && (
                <a
                  href={activeModalEvent.org_link || activeModalEvent.source_url}
                  target="_blank"
                  rel="noreferrer"
                  className="miniapp-sheet-btn-primary"
                  onClick={() => triggerHaptic('medium')}
                >
                  Купить билет / Перейти к событию ↗
                </a>
              )}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
