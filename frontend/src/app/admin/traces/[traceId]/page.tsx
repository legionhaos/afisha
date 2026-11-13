import Link from 'next/link';
import '../../admin.css';
export default function TracePage() {
  return <main className="admin-shell"><div className="admin-wrap"><nav className="admin-nav"><Link href="/admin">← Панель управления</Link></nav><h1>Трассировка запроса</h1><div className="admin-notice" role="status"><strong>Просмотр трассировки пока недоступен</strong><p>Необходимо подключить защищённый API трассировок и авторизацию.</p></div></div></main>;
}
