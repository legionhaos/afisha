'use client';
import { useState, type FormEvent } from 'react';
import Link from 'next/link';
import { isDemoMode } from '@/lib/api-client';
import AgentChatDrawer from '@/components/AgentChatDrawer';
import PixelOrnament from '@/components/PixelOrnament';
import SiteHeader from '@/components/SiteHeader';
import './catalog.css';
import './home.css';

const directions = [
  { name: 'Концерты', text: 'Музыка и живые выступления', mark: '01', href: '/events?category=Концерты' },
  { name: 'Театр', text: 'Спектакли и постановки', mark: '02', href: '/events?category=Театр' },
  { name: 'Выставки', text: 'Искусство и новые открытия', mark: '03', href: '/events?category=Выставки' },
  { name: 'Мастер-классы', text: 'Создавайте и пробуйте', mark: '04', href: '/events?category=Мастер-классы' },
  { name: 'Спорт', text: 'Соревнования и спортивные события', mark: '05', href: '/events?category=Спорт' },
  { name: 'Кино', text: 'Фильмы, кинотеатры и сеансы', mark: '06', href: '/cinema' },
  { name: 'Экскурсии', text: 'Организации и путешествия по республике', mark: '07', href: '/excursions' },
];
export default function HomePage() {
  const [question,setQuestion] = useState('');
  const [launchRequest,setLaunchRequest] = useState<{id:number;text:string}>();
  function openAssistant(text = '') { setLaunchRequest({ id: Date.now(), text }); }
  function askAssistant(event:FormEvent<HTMLFormElement>) { event.preventDefault(); openAssistant(question.trim()); }
  return <main className="hybrid-page"><SiteHeader />
    <section className="home-hero"><div className="home-hero-copy"><p className="home-kicker">АФИША БАШКОРТОСТАНА</p><h1>Культура<br/><em>в вашем ритме.</em></h1><p>Открывайте события республики или расскажите помощнику, что вы ищете.</p><form className="home-search" onSubmit={askAssistant}><label className="home-sr" htmlFor="home-question">Запрос помощнику</label><span aria-hidden="true">⌕</span><input id="home-question" value={question} onChange={event=>setQuestion(event.target.value)} placeholder="Например, концерт для всей семьи"/><button type="submit">Спросить ↗</button></form><small>Запрос откроется в чате — вы сможете проверить его перед отправкой.</small></div><div className="home-art" aria-hidden="true"><span>КУЛЬТУРА<br/>РЯДОМ</span><PixelOrnament className="home-art-ornament"/><small>БАШКОРТОСТАН / 02</small></div></section>
    <div className="home-body"><section className="direction-section" aria-labelledby="directions-title"><div className="direction-heading"><div><p className="home-kicker">ВЫБИРАЙТЕ ВПЕЧАТЛЕНИЯ</p><h2 id="directions-title">Направления<span>.</span></h2></div><p>Культурные и спортивные события республики</p></div><div className="direction-grid">{directions.map(direction=><Link key={direction.name} className="direction-card" href={direction.href}><div className="direction-art" aria-hidden="true"><PixelOrnament className="direction-ornament"/><span>{direction.mark} / 07</span></div><div className="direction-copy"><small>АФИША БАШКОРТОСТАНА</small><h3>{direction.name}</h3><p>{direction.text}</p><span className="direction-link">Открыть раздел ↗</span></div></Link>)}</div></section>
      <div className="home-content home-bottom"><section><p className="home-kicker">ВСЯ АФИША</p><h2>Все события в одном месте</h2><p>Ищите по городу, дате и интересам.</p><Link className="catalog-button" href="/events">Открыть каталог ↗</Link></section></div>
    </div><footer className="home-footer"><Link href="/">✳ АФИША БАШКОРТОСТАНА</Link><span>Культура начинается здесь.</span><Link href="/widget">Виджет для сайта ↗</Link></footer><AgentChatDrawer launchRequest={launchRequest}/></main>;
}
