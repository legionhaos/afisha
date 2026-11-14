'use client';

import { useState } from 'react';
import './logos.css';

const concepts = [
  { name: 'Цветок курая', tag: 'СЕМЬ ЛУЧЕЙ', description: 'Семь лепестков собираются в ясный, компактный знак.', color: 'lime' },
  { name: 'Курай в круге', tag: 'СОЦВЕТИЕ + КРУГ', description: 'Ритм семи лучей внутри мягкого круглого силуэта.', color: 'violet' },
  { name: 'Орнамент сцены', tag: 'РОМБ + СТУПЕНИ', description: 'Ромб в обрамлении ступенчатой геометрии.', color: 'orange' },
  { name: 'Крылья птицы', tag: 'ПО ВАШЕМУ РЕФЕРЕНСУ', description: 'Плотный силуэт с центральным пером и завитками — по мотивам присланной птицы.', color: 'blue' },
  { name: 'Ткань культуры', tag: 'РОМБЫ + РИТМ', description: 'Три ромба и ступени складываются в лаконичный узор.', color: 'pink' },
  { name: 'Луч и ромб', tag: 'КУРАЙ + ГЕОМЕТРИЯ', description: 'Семилучевое соцветие встречается с формой ромба.', color: 'yellow' },
  { name: 'Кош ҡанат', tag: 'КОНТУР ПО РЕФЕРЕНСУ', description: 'Контурная версия того же мотива с изогнутыми крыльями.', color: 'green' },
  { name: 'Ступени полёта', tag: 'КРЫЛЬЯ + ОРНАМЕНТ', description: 'Изогнутые крылья соединены ступенчатым ромбом.', color: 'peach' },
];

function Mark({ index }: { index: number }) {
  const common = { width: 42, height: 42, viewBox: '0 0 42 42', fill: 'none', 'aria-hidden': true as const };
  const flower = (center: number, radius: number, length: number, width: number) => <g fill="currentColor">{Array.from({ length: 7 }, (_, i) => <ellipse key={i} cx={center} cy={center - radius} rx={width} ry={length} transform={`rotate(${i * 360 / 7} ${center} ${center})`}/>)}<circle cx={center} cy={center} r={width + 1}/></g>;
  if (index === 0) return <svg {...common}>{flower(21, 10, 7, 2.8)}</svg>;
  if (index === 1) return <svg {...common}><circle cx="21" cy="21" r="18" stroke="currentColor" strokeWidth="3"/>{flower(21, 8, 5, 2.2)}</svg>;
  if (index === 2) return <svg {...common}><path d="M21 3 39 21 21 39 3 21 21 3Zm0 7L10 21l11 11 11-11L21 10Z" fill="currentColor" fillRule="evenodd"/><path d="M2 12h5V7h5M30 7h5v5M2 30h5v5h5M30 35h5v-5" stroke="currentColor" strokeWidth="3"/></svg>;
  if (index === 3) return <svg {...common}><path d="M21 3C18 5 18 8 19 12C14 9 8 11 6 16C4 20 5 27 2 36C6 34 9 31 10 25C12 29 17 28 17 24C17 22 16 21 15 21C15 23 12 23 12 21C12 18 17 17 19 21C21 25 18 31 13 37C18 35 20 31 21 27C22 31 24 35 29 37C24 31 21 25 23 21C25 17 30 18 30 21C30 23 27 23 27 21C26 21 25 22 25 24C25 28 30 29 32 25C33 31 36 34 40 36C37 27 38 20 36 16C34 11 28 9 23 12C24 8 24 5 21 3Z" fill="currentColor"/></svg>;
  if (index === 4) return <svg {...common}><path d="M21 4 30 13 21 22 12 13 21 4ZM8 20l6 6-6 6-6-6 6-6Zm26 0 6 6-6 6-6-6 6-6ZM21 25l7 7-7 7-7-7 7-7Z" fill="currentColor"/><path d="M2 15V9h6M40 15V9h-6" stroke="currentColor" strokeWidth="3"/></svg>;
  if (index === 5) return <svg {...common}><path d="M21 2 40 21 21 40 2 21 21 2Z" stroke="currentColor" strokeWidth="3"/>{flower(21, 6, 4, 1.7)}</svg>;
  if (index === 6) return <svg {...common}><path d="M21 3C18 5 17 9 19 13C15 10 9 11 7 14C4 17 5 23 4 28L2 35C7 33 10 30 11 25C13 27 16 25 15 23C14 25 11 24 12 22C13 19 18 19 19 23C20 27 16 33 11 38C16 37 19 34 21 31C23 34 26 37 31 38C26 33 22 27 23 23C24 19 29 19 30 22C31 24 28 25 27 23C26 25 29 27 31 25C32 30 35 33 40 35L38 28C37 23 38 17 35 14C33 11 27 10 23 13C25 9 24 5 21 3Z" stroke="currentColor" strokeWidth="2.4" strokeLinecap="round" strokeLinejoin="round"/></svg>;
  return <svg {...common}><path d="M17 28C9 28 4 23 3 13c4 4 8 6 13 7M25 28c8 0 13-5 14-15-4 4-8 6-13 7" stroke="currentColor" strokeWidth="4" strokeLinecap="round"/><path d="M21 13h3v4h4v4h4v4h-4v4h-4v4h-6v-4h-4v-4h-4v-4h4v-4h4v-4h3Zm0 7-4 4 4 4 4-4-4-4Z" fill="currentColor" fillRule="evenodd"/></svg>;
}

function Logo({ index }: { index: number }) {
  return <div className={`logo-lockup logo-${index}`}><Mark index={index}/><span>Bash <b>Афиш</b></span></div>;
}

export default function LogosPage() {
  const [selected, setSelected] = useState<number[]>([]);
  const toggle = (i: number) => setSelected(selected.includes(i) ? selected.filter(item => item !== i) : [...selected, i]);
  return <main className="logos-page">
    <header className="topbar"><a className="top-brand" href="#top"><span className="brand-dot">✳</span> Bash Афиш <small> / дизайн-лаборатория</small></a><span className="top-right">КУЛЬТУРА В НОВОМ ОБЛИКЕ <i>✳</i></span></header>
    <section className="hero" id="top"><div className="hero-copy"><div className="eyebrow"><span className="live-dot"/> ТВОРЧЕСКОЕ ИССЛЕДОВАНИЕ <span className="eyebrow-line"/> 2025</div><h1>У культуры<br/>много <em>лиц.</em></h1><p>Ищем визуальный язык для портала <strong>«Bash Афиш».</strong> Восемь разных характеров — какой ближе вам?</p><a className="hero-link" href="#concepts">СМОТРЕТЬ ВАРИАНТЫ <span>↘</span></a></div><div className="hero-art" aria-hidden="true"><div className="art-orbit orbit-one"/><div className="art-orbit orbit-two"/><span className="art-star">✳</span><span className="art-label">ИДЕИ ДЛЯ<br/>КУЛЬТУРЫ <b>↗</b></span><span className="art-index">01 — 08</span></div></section>
    <section className="intro" id="concepts"><div><div className="section-kicker">01 / КОЛЛЕКЦИЯ КОНЦЕПЦИЙ</div><h2>Восемь взглядов.<br/><em>Одна афиша.</em></h2></div><div className="intro-side"><span className="asterisk">✳</span><p>Авторские эскизы по мотивам башкирского орнамента, курая и образа птицы. Это не официальные и не исторически точные символы, а концепции для обсуждения.</p><div className="selection-count">ВЫБРАНО ДЛЯ ОБСУЖДЕНИЯ <b>{String(selected.length).padStart(2, '0')} / 08</b></div></div></section>
    <section className="gallery" aria-label="Варианты логотипа">{concepts.map((concept, i) => <article className="concept" key={concept.name}><div className="card-meta"><span>КОНЦЕПЦИЯ {String(i + 1).padStart(2, '0')}</span><span>{concept.tag}</span></div><div className={`logo-stage ${concept.color}`}><span className="stage-corner">BА / {String(i + 1).padStart(2, '0')}</span><Logo index={i}/><span className="stage-bottom">КУЛЬТУРА БЛИЖЕ, ЧЕМ КАЖЕТСЯ</span></div><div className="card-heading"><div><h3>{concept.name}</h3><p>{concept.description}</p></div><button onClick={() => toggle(i)} aria-pressed={selected.includes(i)} className={selected.includes(i) ? 'picked' : ''} aria-label={`${selected.includes(i) ? 'Убрать из выбранного' : 'Выбрать'}: ${concept.name}`}>{selected.includes(i) ? '✓' : '+'}</button></div><div className="preview-label"><span>В КОНТЕКСТЕ</span><span>DESKTOP / MOBILE</span></div><div className="previews"><div className="desktop-preview"><div className="mock-header"><Logo index={i}/><div className="mock-nav">События&nbsp;&nbsp; Места&nbsp;&nbsp; Журнал</div><span className="mock-search">⌕</span></div><div className="mock-body"><span>ВАШ ПУТЕВОДИТЕЛЬ ПО КУЛЬТУРЕ</span><strong>Время<br/><em>впечатлений.</em></strong><div className="mock-lines"/></div><div className={`mock-shape ${concept.color}`}>✳</div></div><div className="mobile-preview"><div className="mobile-top"><Logo index={i}/><span>☰</span></div><div className="mobile-body"><small>КУЛЬТУРА РЯДОМ</small><strong>Время<br/><em>впечатлений.</em></strong><div className={`mobile-shape ${concept.color}`}>✳</div></div></div></div></article>)}</section>
    <section className="outro"><span className="outro-star">✳</span><div><div className="section-kicker">ПРОДОЛЖЕНИЕ СЛЕДУЕТ</div><h2>Какой вариант<br/><em>ваш?</em></h2><p>Отметьте понравившиеся концепции, чтобы вернуться к ним при обсуждении. Выбор остаётся за вами.</p></div><a href="#top">НАВЕРХ ↑</a></section><footer><strong>✳ &nbsp; Bash Афиш</strong><span>КУЛЬТУРА НАЧИНАЕТСЯ ЗДЕСЬ</span><span>КОНЦЕПЦИИ ДЛЯ ОБСУЖДЕНИЯ / 01—08</span></footer>
  </main>;
}
