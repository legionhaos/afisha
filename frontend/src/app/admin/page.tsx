import Link from 'next/link';
import './admin.css';

export default function AdminPage() {
  return <main className="admin-shell"><div className="admin-wrap">
    <nav className="admin-nav"><Link href="/">← К афише</Link><span>Панель управления</span></nav>
    <p className="admin-eyebrow">Администрирование</p><h1>Управление афишей</h1>
    <div className="admin-notice" role="status"><strong>Сервер администрирования не подключён</strong><p>Авторизация и управление данными пока недоступны. Эта страница не защищает доступ к административным функциям.</p></div>
    <section className="admin-grid" aria-label="Разделы администрирования">
      <article className="admin-card"><span>01</span><h2>Импорт событий</h2><p>Информация о загрузке событий из внешних источников.</p><Link href="/admin/import">Открыть раздел →</Link></article>
      <article className="admin-card"><span>02</span><h2>События</h2><p>Просмотр и редактирование событий появятся после подключения сервера.</p><strong className="admin-unavailable">Недоступно</strong></article>
    </section>
  </div></main>;
}
