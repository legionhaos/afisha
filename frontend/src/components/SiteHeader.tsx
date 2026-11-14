'use client';
import { useEffect, useState } from 'react';
import Link from 'next/link';

export function useSelectedCity() {
  const [city, setCity] = useState('');
  useEffect(() => {
    const sync = () => setCity(localStorage.getItem('afisha-city') || '');
    sync();
    window.addEventListener('afisha-city-change', sync);
    window.addEventListener('storage', sync);
    return () => { window.removeEventListener('afisha-city-change', sync); window.removeEventListener('storage', sync); };
  }, []);
  return city;
}
export default function SiteHeader() {
  const city = useSelectedCity();
  const [cities, setCities] = useState<string[]>([]);
  useEffect(() => {
    const controller = new AbortController();
    fetch('/api/v1/dictionaries/cities', { signal: controller.signal }).then(response => {
      if (!response.ok) throw new Error('cities unavailable');
      return response.json() as Promise<Array<{ name: string }>>;
    }).then(data => setCities(data.map(item => item.name).sort((a, b) => {
      if (a === 'Уфа') return b === 'Уфа' ? 0 : -1;
      if (b === 'Уфа') return 1;
      return a.localeCompare(b, 'ru');
    }))).catch(() => {});
    return () => controller.abort();
  }, []);
  function changeCity(value: string) {
    if (value) localStorage.setItem('afisha-city', value); else localStorage.removeItem('afisha-city');
    window.dispatchEvent(new Event('afisha-city-change'));
  }
  return <header className="home-header"><Link className="home-brand" href="/" aria-label="Bash Афиш — главная"><svg className="home-brand-mark" viewBox="0 0 42 42" aria-hidden="true"><path d="M21 3C18 5 18 8 19 12C14 9 8 11 6 16C4 20 5 27 2 36C6 34 9 31 10 25C12 29 17 28 17 24C17 22 16 21 15 21C15 23 12 23 12 21C12 18 17 17 19 21C21 25 18 31 13 37C18 35 20 31 21 27C22 31 24 35 29 37C24 31 21 25 23 21C25 17 30 18 30 21C30 23 27 23 27 21C26 21 25 22 25 24C25 28 30 29 32 25C33 31 36 34 40 36C37 27 38 20 36 16C34 11 28 9 23 12C24 8 24 5 21 3Z" fill="currentColor"/></svg><strong>Bash Афиш</strong></Link><nav aria-label="Основная навигация"><Link href="/">Главная</Link><Link href="/events">События</Link><label className="city-select"><svg className="city-select-icon" viewBox="0 0 24 24" fill="none" aria-hidden="true"><path d="M19 10c0 5-7 10-7 10S5 15 5 10a7 7 0 1 1 14 0Z" stroke="currentColor" strokeWidth="1.7"/><circle cx="12" cy="10" r="2.2" stroke="currentColor" strokeWidth="1.7"/></svg><select aria-label="Выбрать город" value={city} onChange={event => changeCity(event.target.value)}><option value="">Все города</option>{city && !cities.includes(city) && <option value={city}>{city}</option>}{cities.map(name => <option key={name} value={name}>{name}</option>)}</select><svg className="city-select-chevron" viewBox="0 0 16 16" fill="none" aria-hidden="true"><path d="m4 6 4 4 4-4" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round"/></svg></label></nav></header>;
}
