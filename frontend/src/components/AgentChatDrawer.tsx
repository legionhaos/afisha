'use client';

import { useEffect, useRef, useState, type FormEvent, type KeyboardEvent } from 'react';
import { streamChat } from '../lib/sse-client';
import './chat.css';

type Message = { id: number; role: 'user' | 'assistant'; text: string };

export default function AgentChatDrawer({ launchRequest }: { launchRequest?: { id: number; text: string } }) {
  const [open, setOpen] = useState(false);
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState('');
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);
  const thread = useRef<string | null>(null);
  const pendingCityQuery = useRef<string | null>(null);
  const controller = useRef<AbortController | null>(null);
  const nextId = useRef(0);
  const launcher = useRef<HTMLButtonElement>(null);
  const closeButton = useRef<HTMLButtonElement>(null);
  const dialog = useRef<HTMLElement>(null);
  const end = useRef<HTMLDivElement>(null);

  useEffect(() => () => controller.current?.abort(), []);
  useEffect(() => {
    if (launchRequest) { setInput(launchRequest.text); setOpen(true); }
  }, [launchRequest]);
  useEffect(() => { if (open) closeButton.current?.focus(); }, [open]);
  useEffect(() => { if (open) end.current?.scrollIntoView({ block: 'end' }); }, [messages, open, error]);

  function close() {
    setOpen(false);
    launcher.current?.focus();
  }
  function clear() {
    controller.current?.abort();
    controller.current = null;
    thread.current = null;
    pendingCityQuery.current = null;
    setMessages([]);
    setInput('');
    setError('');
    setLoading(false);
  }
  function keys(event: KeyboardEvent<HTMLElement>) {
    if (event.key === 'Escape') { event.preventDefault(); close(); return; }
    if (event.key !== 'Tab') return;
    const elements = dialog.current?.querySelectorAll<HTMLElement>('button:not(:disabled), textarea:not(:disabled), input:not(:disabled), [href], [tabindex]:not([tabindex="-1"])');
    if (!elements?.length) return;
    const first = elements[0];
    const last = elements[elements.length - 1];
    if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last.focus(); }
    else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first.focus(); }
  }
  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const message = input.trim();
    if (!message || controller.current) return;
    const userId = ++nextId.current;
    const assistantId = ++nextId.current;
    const request = new AbortController();
    controller.current = request;
    setMessages(previous => [...previous, { id: userId, role: 'user', text: message }]);
    setInput(''); setError(''); setLoading(true);
    try {
      const query = pendingCityQuery.current ? `${pendingCityQuery.current}. Город: ${message}` : message;
      pendingCityQuery.current = null;
      await streamChat({
        message: query, threadId: thread.current, signal: request.signal,
        onClarifyingQuestion: question => { if (controller.current === request && question?.toLowerCase().includes('город')) pendingCityQuery.current = query; },
        onThreadId: id => { if (controller.current === request) thread.current = id; },
        onText: text => {
          if (controller.current !== request) return;
          setMessages(previous => {
            const existing = previous.find(item => item.id === assistantId);
            return existing
              ? previous.map(item => item.id === assistantId ? { ...item, text: item.text + text } : item)
              : [...previous, { id: assistantId, role: 'assistant', text }];
          });
        },
      });
    } catch (err) {
      if (!request.signal.aborted && controller.current === request) {
        setError(err instanceof Error ? err.message : 'Не удалось получить ответ. Попробуйте позже.');
      }
    } finally {
      if (controller.current === request) { controller.current = null; setLoading(false); }
    }
  }

  return <>
    <button ref={launcher} className="agent-chat-launcher" type="button" onClick={() => setOpen(true)} aria-haspopup="dialog" aria-expanded={open}>
      Чат с помощником
    </button>
    {open && <div className="agent-chat-overlay" onMouseDown={event => { if (event.target === event.currentTarget) close(); }}>
      <section ref={dialog} className="agent-chat" role="dialog" aria-modal="true" aria-labelledby="agent-chat-title" onKeyDown={keys}>
        <header className="agent-chat-header">
          <div><h2 id="agent-chat-title">Помощник по афише</h2><p>Поможем найти событие</p></div>
          <button ref={closeButton} className="agent-chat-icon" type="button" onClick={close} aria-label="Закрыть чат">×</button>
        </header>
        <div className="agent-chat-messages" role="log" aria-label="Сообщения чата" aria-live="polite" aria-relevant="additions text">
          {messages.length === 0 && <p className="agent-chat-empty">Расскажите, какое событие вы ищете.</p>}
          {messages.map(item => <div key={item.id} className={`agent-chat-message agent-chat-message--${item.role}`}><span className="agent-chat-sr">{item.role === 'user' ? 'Вы: ' : 'Помощник: '}</span>{item.text}</div>)}
          {loading && <p className="agent-chat-status" role="status">Ожидаем ответ…</p>}
          {error && <p className="agent-chat-error" role="alert">{error}</p>}
          <div ref={end} />
        </div>
        <form className="agent-chat-form" onSubmit={submit}>
          <label className="agent-chat-sr" htmlFor="agent-chat-input">Ваше сообщение</label>
          <textarea id="agent-chat-input" value={input} onChange={event => setInput(event.target.value)} placeholder="Напишите сообщение" rows={2} maxLength={4000} />
          <div className="agent-chat-actions"><button type="button" onClick={clear}>Очистить чат</button><button type="submit" disabled={loading || !input.trim()}>Отправить</button></div>
        </form>
      </section>
    </div>}
  </>;
}

