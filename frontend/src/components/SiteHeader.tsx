import Link from 'next/link';
export default function SiteHeader() {
  return <header className="home-header"><Link className="home-brand" href="/" aria-label="Афиша Башкортостана — главная"><span aria-hidden="true">✳</span><strong>афиша</strong><small>БАШКОРТОСТАНА</small></Link><nav aria-label="Основная навигация"><Link href="/">Главная</Link><Link href="/events">События</Link></nav></header>;
}
