import Link from 'next/link';
import SiteHeader from '@/components/SiteHeader';
import AgentChatDrawer from '@/components/AgentChatDrawer';
import '../home.css';
import '../inner.css';
export default function ExcursionsPage(){return <main className="hybrid-page"><SiteHeader/><div className="inner-page"><Link className="inner-back" href="/">← Главная</Link><p className="home-kicker">ОТКРЫВАЙТЕ РЕСПУБЛИКУ</p><h1>Экскурсии<span>.</span></h1><p className="inner-lead">Организации, которые проводят экскурсии в Башкортостане.</p><div className="service-empty" role="status"><span aria-hidden="true">↗</span><div><h3>Список организаций пока не загружен</h3><p>Контакты и ссылки появятся после подключения проверенного справочника.</p></div></div></div><AgentChatDrawer/></main>}
