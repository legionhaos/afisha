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
    }).then(data => setCities(data.map(item => item.name))).catch(() => {});
    return () => controller.abort();
  }, []);
  function changeCity(value: string) {
    if (value) localStorage.setItem('afisha-city', value); else localStorage.removeItem('afisha-city');
    window.dispatchEvent(new Event('afisha-city-change'));
  }
  return <header className="home-header"><Link className="home-brand" href="/" aria-label="Афиша Башкортостана — главная"><span aria-hidden="true">✳</span><strong>афиша</strong><small>БАШКОРТОСТАНА</small></Link><nav aria-label="Основная навигация"><Link href="/">Главная</Link><Link href="/events">События</Link><label className="city-select"><span>Город</span><select aria-label="Выбрать город" value={city} onChange={event => changeCity(event.target.value)}><option value="">Все города</option>{city && !cities.includes(city) && <option value={city}>{city}</option>}{cities.map(name => <option key={name} value={name}>{name}</option>)}</select></label></nav></header>;
}
