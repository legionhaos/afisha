import { NextRequest } from 'next/server';

export const dynamic = 'force-dynamic';

type Context = { params: Promise<{ path: string[] }> };

async function proxy(request: NextRequest, context: Context) {
  const { path } = await context.params;
  const method = request.method;
  const events = path[0] === 'v1' && path[1] === 'events' && path.length <= 3 && method === 'GET';
  const dictionaries = path[0] === 'v1' && path[1] === 'dictionaries' && path.length <= 3 && method === 'GET';
  const chat = path.join('/') === 'v1/chat/stream' && method === 'POST';
  if (!events && !dictionaries && !chat) return new Response('Not found', { status: 404 });
  if (chat && Number(request.headers.get('content-length') || 0) > 16384) return new Response('Request too large', { status: 413 });
  const base = process.env.BACKEND_URL || 'http://localhost:8000';
  const target = `${base}/api/${path.map(encodeURIComponent).join('/')}${request.nextUrl.search}`;
  try {
    const body = chat ? await request.text() : undefined;
    if (body && new TextEncoder().encode(body).length > 16384) return new Response('Request too large', { status: 413 });
    const upstream = await fetch(target, {
      method,
      headers: { accept: request.headers.get('accept') || 'application/json', ...(body ? { 'content-type': 'application/json' } : {}) },
      body,
      cache: 'no-store',
      signal: request.signal,
    });
    const headers = new Headers();
    for (const key of ['content-type', 'cache-control', 'etag']) {
      const value = upstream.headers.get(key);
      if (value) headers.set(key, value);
    }
    return new Response(upstream.body, { status: upstream.status, headers });
  } catch {
    return new Response('Backend unavailable', { status: 502 });
  }
}

export const GET = proxy;
export const POST = proxy;
