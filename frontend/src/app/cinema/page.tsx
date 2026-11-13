'use client';
import { useState } from 'react';
import Link from 'next/link';
import SiteHeader from '@/components/SiteHeader';
import AgentChatDrawer from '@/components/AgentChatDrawer';
import '../home.css';
import '../inner.css';
export default function CinemaPage(){const [mode,setMode]=useState<'films'|'cinemas'>('films');return <main className="hybrid-page"><SiteHeader/><div className="inner-page"><Link className="inner-back" href="/">← Главная</Link><p className="home-kicker">КУЛЬТУРА НА БОЛЬШОМ ЭКРАНЕ</p><h1>Кино<span>.</span></h1><p className="inner-lead">Выберите фильм или начните поиск с кинотеатра.</p><div className="service-tabs" role="group" aria-label="Способ выбора кино"><button aria-pressed={mode==='films'} onClick={()=>setMode('films')}>По фильму</button><button aria-pressed={mode==='cinemas'} onClick={()=>setMode('cinemas')}>По кинотеатру</button></div><div className="service-empty" role="status"><span aria-hidden="true">▣</span><div><h3>{mode==='films'?'Фильмы пока не загружены':'Кинотеатры пока не загружены'}</h3><p>{mode==='films'?'Фильмы и сеансы появятся после подключения источника данных.':'Кинотеатры и их сеансы появятся после подключения источника данных.'}</p></div></div></div><AgentChatDrawer/></main>}
