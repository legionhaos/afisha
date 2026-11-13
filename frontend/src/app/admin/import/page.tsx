import Link from 'next/link';
import '../admin.css';

export default function AdminImportPage() {
  return <main className="admin-shell"><div className="admin-wrap">
    <nav className="admin-nav"><Link href="/admin">← Администрирование</Link><Link href="/">К афише</Link></nav>
    <p className="admin-eyebrow">Администрирование / Импорт</p><h1>Импорт событий</h1>
    <div className="admin-notice" role="status"><strong>Импорт пока недоступен</strong><p>Сервер администрирования не подключён. Загрузка файлов и запуск импорта не выполняются.</p></div>
    <section className="admin-card admin-info"><h2>Что потребуется</h2><p>После подключения серверной части здесь можно будет настроить источник данных и отслеживать результат импорта. Формат и способ загрузки будут определены при интеграции.</p></section>
  </div></main>;
}
