// Protocol assumption: POST {message, thread_id}; SSE data is plain text or
// JSON with delta/text/content and optional thread_id. [DONE] or event: done
// ends the stream; event: error signals failure. JSON responses may instead
// contain message/answer/text/content and thread_id.
export interface ChatStreamOptions {
  message: string;
  threadId: string | null;
  signal?: AbortSignal;
  endpoint?: string;
  onText: (text: string) => void;
  onThreadId?: (id: string) => void;
}

export async function streamChat(options: ChatStreamOptions): Promise<void> {
  let response: Response;
  const threadId = options.threadId || crypto.randomUUID();
  options.onThreadId?.(threadId);
  try {
    response = await fetch(options.endpoint || '/api/v1/chat/stream', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', Accept: 'text/event-stream, application/json' },
      body: JSON.stringify({ message: options.message, thread_id: threadId, user_identifier: `web:${threadId}` }),
      signal: options.signal,
    });
  } catch (error) {
    if (options.signal?.aborted) throw error;
    throw new Error('Не удалось подключиться к сервису чата. Проверьте соединение и попробуйте снова.');
  }
  if (!response.ok) throw new Error(`Сервис чата недоступен (HTTP ${response.status}). Попробуйте позже.`);

  let received = false;
  let done = false;
  const handle = (data: string, event = 'message') => {
    if (done) return;
    if (data.trim() === '[DONE]' || event === 'done') { done = true; return; }
    if (event === 'status') return;
    if (event === 'cards') {
      try {
        const cards = JSON.parse(data) as Array<{ event?: { title?: string; city?: string; date_start?: string } }>;
        const lines = cards.map(({ event: card }) => card?.title ? `• ${card.title}${card.city ? ` — ${card.city}` : ''}${card.date_start ? ` (${new Date(card.date_start).toLocaleDateString('ru-RU', { timeZone: 'Asia/Yekaterinburg' })})` : ''}` : '').filter(Boolean);
        if (lines.length) { received = true; options.onText(`\n\n${lines.join('\n')}`); }
      } catch { /* Ignore malformed card payloads. */ }
      return;
    }
    let value: unknown = data;
    try { value = JSON.parse(data); } catch { /* Plain-text SSE data. */ }
    if (event === 'error') {
      const message = typeof value === 'string' ? value : (value as { message?: string })?.message;
      throw new Error(message || 'Сервис чата сообщил об ошибке.');
    }
    if (typeof value === 'string') {
      if (value) { received = true; options.onText(value); }
      return;
    }
    if (!value || typeof value !== 'object') return;
    const item = value as Record<string, unknown>;
    if (typeof item.thread_id === 'string') options.onThreadId?.(item.thread_id);
    if (item.error) throw new Error(typeof item.error === 'string' ? item.error : 'Сервис чата сообщил об ошибке.');
    if (item.done === true || item.type === 'done') done = true;
    const text = item.delta ?? item.text ?? item.content ?? item.answer ?? item.message;
    if (typeof text === 'string' && text) { received = true; options.onText(text); }
  };

  if (response.headers.get('content-type')?.toLowerCase().includes('application/json')) {
    handle(JSON.stringify(await response.json()));
  } else {
    if (!response.body) throw new Error('Сервис чата вернул пустой ответ.');
    const reader = response.body.getReader();
    const decoder = new TextDecoder();
    let buffer = '';
    let event = '';
    let data: string[] = [];
    const line = (value: string) => {
      if (value === '') {
        if (data.length) handle(data.join('\n'), event || 'message');
        event = ''; data = [];
      } else if (!value.startsWith(':')) {
        const colon = value.indexOf(':');
        const field = colon < 0 ? value : value.slice(0, colon);
        let content = colon < 0 ? '' : value.slice(colon + 1);
        if (content.startsWith(' ')) content = content.slice(1);
        if (field === 'data') data.push(content);
        else if (field === 'event') event = content;
      }
    };
    try {
      while (!done) {
        const chunk = await reader.read();
        buffer += decoder.decode(chunk.value, { stream: !chunk.done });
        let match: RegExpExecArray | null;
        while ((match = /\r\n|\n|\r(?!$)/.exec(buffer))) {
          line(buffer.slice(0, match.index));
          buffer = buffer.slice(match.index + match[0].length);
        }
        if (chunk.done) {
          if (buffer.endsWith('\r')) buffer = buffer.slice(0, -1);
          if (buffer) line(buffer);
          if (data.length) line('');
          break;
        }
      }
    } finally {
      if (done) await reader.cancel().catch(() => {});
      reader.releaseLock();
    }
  }
  if (!received) throw new Error('Сервис чата не вернул ответ. Попробуйте позже.');
}

