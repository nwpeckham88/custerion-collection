import { env } from '$env/dynamic/private';
import type { RequestHandler } from './$types';

export const POST: RequestHandler = async ({ request, fetch }) => {
  let body: unknown;
  try {
    body = await request.json();
  } catch {
    return new Response(JSON.stringify({ detail: 'Request body must be valid JSON' }), {
      status: 400,
      headers: { 'content-type': 'application/json' }
    });
  }

  const target = `${env.BACKEND_API_URL ?? 'http://localhost:8000'}/deep-dive/start`;

  try {
    const response = await fetch(target, {
      method: 'POST',
      headers: { 'content-type': 'application/json' },
      body: JSON.stringify(body)
    });

    const payload = await response.text();
    const contentType = response.headers.get('content-type') ?? 'application/json';

    return new Response(payload, {
      status: response.status,
      headers: { 'content-type': contentType }
    });
  } catch (error) {
    return new Response(JSON.stringify({ detail: `Backend deep-dive start failed: ${String(error)}` }), {
      status: 502,
      headers: { 'content-type': 'application/json' }
    });
  }
};
