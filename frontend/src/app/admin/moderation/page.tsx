import Link from 'next/link';
import '../admin.css';
export default function ModerationPage() {
  return <main className="admin-shell"><div className="admin-wrap"><nav className="admin-nav"><Link href="/admin">← Панель управления</Link></nav><h1>Модерация</h1><div className="admin-notice" role="status"><strong>Модерация пока недоступна</strong><p>Необходимо согласовать и подключить API модерации и авторизацию на сервере.</p></div></div></main>;
}
