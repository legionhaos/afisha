'use client';

import { useState } from 'react';
import Link from 'next/link';
import PixelOrnament from '@/components/PixelOrnament';
import './showcase.css';

const designs = [
  { id: 'editorial', name: 'Культурный журнал', description: 'Редакционная афиша с крупной типографикой и обложками.', title: 'Культура\nв деталях', kicker: 'РЕСПУБЛИКА БАШКОРТОСТАН · КУЛЬТУРНЫЙ ЖУРНАЛ', cta: 'Листать афишу' },
  { id: 'heritage', name: 'Наследие', description: 'Современная трактовка орнамента и тёплая природная палитра.', title: 'Традиции.\nНовые истории.', kicker: 'АФИША КУЛЬТУРЫ БАШКОРТОСТАНА', cta: 'Открыть события' },
  { id: 'poster', name: 'Городской плакат', description: 'Смелый плакатный стиль: крупные заголовки и контрастные блоки.', title: 'ВЫХОДИ\nВ ГОРОД!', kicker: 'ВСТРЕЧАЕМСЯ НА СОБЫТИЯХ', cta: 'Выбрать событие' },
  { id: 'minimal', name: 'Чистая афиша', description: 'Спокойный минималистичный интерфейс, где главные — события.', title: 'Культура\nрядом с вами', kicker: 'АФИША РЕСПУБЛИКИ', cta: 'Смотреть события' },
  { id: 'night', name: 'Вечерняя сцена', description: 'Тёмная театральная композиция со светлыми акцентами.', title: 'Сегодня —\nваш выход.', kicker: 'СОБЫТИЯ ПОСЛЕ ЗАНАВЕСА И НЕ ТОЛЬКО', cta: 'В афишу' },
  { id: 'mosaic', name: 'Мозаика', description: 'Разноцветные модульные блоки для разных направлений культуры.', title: 'Всё, что\nвдохновляет', kicker: 'СОБИРАЕМ ВПЕЧАТЛЕНИЯ ВМЕСТЕ', cta: 'Исследовать' },
  { id: 'newspaper', name: 'Культурная газета', description: 'Колонки, разделители и выразительные заголовки как у издания.', title: 'Афиша\nБашкортостана', kicker: 'КУЛЬТУРА · ЛЮДИ · МЕСТА', cta: 'Читать афишу' },
  { id: 'nature', name: 'Просторы', description: 'Природные оттенки и органичные формы для регионального сервиса.', title: 'Ближе к\nсвоей культуре', kicker: 'МЕСТА, ЛЮДИ, ВПЕЧАТЛЕНИЯ', cta: 'Найти событие' },
  { id: 'digital', name: 'Цифровой орнамент', description: 'Пиксельный мотив как современный акцент, а не стиль всей страницы.', title: 'Культура\nв новом ритме', kicker: 'ТРАДИЦИИ × СОВРЕМЕННОСТЬ', cta: 'Открыть афишу' },
  { id: 'calendar', name: 'Календарь', description: 'Практичный вариант с акцентом на даты и быстрый выбор.', title: 'Есть планы?\nТеперь есть.', kicker: 'ПЛАНИРУЙТЕ СВОБОДНОЕ ВРЕМЯ', cta: 'Выбрать дату' },
];
const cards = [
  { category: 'ВЫСТАВКА', title: 'Цвета Башкортостана', city: 'Уфа · Выставочный зал', date: '12 ИЮНЯ', price: 'Бесплатно', number: '01' },
  { category: 'КОНЦЕРТ', title: 'Вечер башкирской музыки', city: 'Уфа · Концертная площадка', date: '13 ИЮНЯ', price: 'от 500 ₽', number: '02' },
  { category: 'ТЕАТР', title: 'Легенда гор', city: 'Стерлитамак · Театр', date: '19 ИЮНЯ', price: 'от 350 ₽', number: '03' },
];

export default function DesignsPage() {
  const [selected, setSelected] = useState(0);
  const design = designs[selected];
  return <main className="design-showcase">
    <header className="showcase-header"><div><Link href="/" className="showcase-back">← Вернуться к афише</Link><p>ВЫБОР НАПРАВЛЕНИЯ</p><h1>Какой будет наша афиша?</h1><span>10 разных концепций интерфейса. Выберите вариант, чтобы посмотреть его ниже.</span></div><span className="showcase-counter">{String(selected + 1).padStart(2, '0')} / 10</span></header>
    <nav className="design-picker" aria-label="Выбрать дизайн">{designs.map((item, index) => <button key={item.id} type="button" onClick={() => setSelected(index)} aria-pressed={selected === index}><span>{String(index + 1).padStart(2, '0')}</span>{item.name}</button>)}</nav>
    <div className="showcase-caption"><div><span>ВАРИАНТ {String(selected + 1).padStart(2, '0')}</span><h2>{design.name}</h2><p>{design.description}</p></div><div className="showcase-actions"><button type="button" onClick={() => setSelected((selected + 9) % 10)} aria-label="Предыдущий дизайн">←</button><button type="button" onClick={() => setSelected((selected + 1) % 10)} aria-label="Следующий дизайн">→</button></div></div>
    <div className={`concept concept--${design.id}`}>
      <header className="concept-header"><div className="concept-brand"><span>✳</span> афиша <small>БАШКОРТОСТАНА</small></div><nav aria-label="Разделы макета"><span>События</span><span>Направления</span><span>О проекте</span></nav><span className="concept-region">Республика Башкортостан ↗</span></header>
      <section className="concept-hero"><div className="concept-copy"><p className="concept-kicker">{design.kicker}</p><h2>{design.title.split('\n').map((line, i) => <span key={line}>{i > 0 && <br />}{line}</span>)}</h2><p className="concept-description">Выставки, концерты, спектакли и другие события республики — найдите что-то своё.</p><a href="#concept-events" className="concept-cta">{design.cta} <span>↗</span></a></div><div className="concept-art" aria-hidden="true"><div className="art-frame"><PixelOrnament className="concept-ornament" /><span className="art-word">КУЛЬТУРА<br />РЯДОМ</span><span className="art-no">02 / 06</span></div></div></section>
      <div className="concept-ticker" aria-hidden="true">КОНЦЕРТЫ <span>✳</span> ТЕАТР <span>✳</span> ВЫСТАВКИ <span>✳</span> СОБЫТИЯ <span>✳</span> КУЛЬТУРА</div>
      <section id="concept-events" className="concept-events"><div className="concept-events-head"><div><p className="concept-kicker">ВАШИ ПЛАНЫ НАЧИНАЮТСЯ ЗДЕСЬ</p><h2>Ближайшие события<span>.</span></h2></div><span>Примеры событий →</span></div><p className="concept-demo">Демонстрационный макет: события вымышлены, элементы поиска и навигации представлены для сравнения дизайна.</p><div className="concept-categories"><span className="active">Все события</span><span>Концерты</span><span>Театр</span><span>Выставки</span><span>Мастер-классы</span></div><div className="concept-grid">{cards.map(card => <article className="concept-card" key={card.number}><div className="concept-card-art"><PixelOrnament className="concept-card-ornament" /><span>{card.number} / 03</span><strong>{card.category}</strong></div><div className="concept-card-content"><div className="concept-meta"><span>{card.category}</span><span>{card.date}</span></div><h3>{card.title}</h3><p>{card.city}</p><div className="concept-card-bottom"><strong>{card.price}</strong><span>↗</span></div></div></article>)}</div></section>
      <footer className="concept-footer"><span>✳ АФИША БАШКОРТОСТАНА</span><span>Культура начинается здесь.</span><span>КОНЦЕПЦИЯ / {String(selected + 1).padStart(2, '0')}</span></footer>
    </div>
    <div className="showcase-bottom"><p>Напишите номер варианта, который понравился, — доработаем его в полноценный интерфейс.</p><Link href="/">Вернуться к работающей афише →</Link></div>
  </main>;
}
