'use client';
import { useState } from 'react';
import Link from 'next/link';
import './sections.css';

const options = [
  { name: 'Навигация по направлениям', text: 'Категории вверху, затем отдельные секции. Понятно, если пользователь уже знает, что ищет.', layout: 'tabs' },
  { name: 'Редакционные блоки', text: 'Каждое направление оформлено как отдельная подборка с собственным ритмом и акцентом.', layout: 'editorial' },
  { name: 'Компактный справочник', text: 'Спокойный список разделов с кратким описанием: минимум прокрутки и быстрый доступ.', layout: 'list' },
  { name: 'Большие плитки', text: 'На первом плане визуальные входы в категории; внутри — мероприятия выбранного направления.', layout: 'tiles' },
];
const sections = [{name:'Концерты',text:'Музыка и живые выступления',mark:'01'}, {name:'Театр',text:'Спектакли и постановки',mark:'02'}, {name:'Выставки',text:'Искусство и новые открытия',mark:'03'}, {name:'Мастер-классы',text:'Создавайте и пробуйте',mark:'04'}];
export default function SectionsPage() {
  const [selected,setSelected] = useState(0);
  const [cinema,setCinema] = useState<'films'|'cinemas'>('films');
  const option = options[selected];
  return <main className="sections-page"><header><Link href="/">← На главную</Link><p>ВЫБОР СТРУКТУРЫ</p><h1>Как оформить разделы?</h1><span>Четыре подхода к организации афиши. Кино и экскурсии есть в каждом варианте.</span></header><nav className="sections-picker" aria-label="Варианты разделов">{options.map((item,i)=><button key={item.name} onClick={()=>setSelected(i)} aria-pressed={selected===i}>{String(i+1).padStart(2,'0')} {item.name}</button>)}</nav><div className="sections-description"><h2>{option.name}</h2><p>{option.text}</p></div><div className={`sections-preview sections-preview--${option.layout}`}><div className="preview-header"><strong>✳ афиша <small>БАШКОРТОСТАНА</small></strong><span>СОБЫТИЯ / КИНО / ЭКСКУРСИИ</span></div><div className="preview-intro"><p>АФИША РЕСПУБЛИКИ</p><h2>Найдите своё событие.</h2><span>Выбирайте впечатления в Башкортостане</span></div>{option.layout==='tabs'&&<div className="preview-tabs">Все события　 Концерты　 Театр　 Выставки　 Кино　 Экскурсии</div>}<div className="preview-content"><h2>Направления</h2><div className="preview-grid">{sections.map((item)=><article key={item.name}><div className="preview-art"><span>✳</span><small>{item.mark} / 04</small></div><div><small>КУЛЬТУРА РЯДОМ</small><h3>{item.name}</h3><p>{item.text}</p><span className="preview-link">Смотреть события ↗</span></div></article>)}</div><section className="preview-cinema"><p className="preview-kicker">КУЛЬТУРА НА БОЛЬШОМ ЭКРАНЕ</p><h2>Кино.</h2><div className="preview-cinema-tabs" role="group" aria-label="Способ выбора кино"><button aria-pressed={cinema==='films'} onClick={()=>setCinema('films')}>По фильму</button><button aria-pressed={cinema==='cinemas'} onClick={()=>setCinema('cinemas')}>По кинотеатру</button></div><div className="preview-empty">{cinema==='films'?'Здесь будет список фильмов и сеансов.':'Здесь будет список кинотеатров и их сеансы.'}</div></section><section className="preview-excursions"><p className="preview-kicker">ОТКРЫВАЙТЕ РЕСПУБЛИКУ</p><h2>Экскурсии.</h2><p>Список организаций и их контакты появятся после подключения проверенного справочника.</p><div className="preview-empty">Организации пока не загружены</div></section></div></div><p className="sections-note">Это макеты структуры, а не реальные данные. Выберите номер — применим его к основной странице.</p></main>;
}
