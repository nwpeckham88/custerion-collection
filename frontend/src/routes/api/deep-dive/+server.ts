import { env } from '$env/dynamic/private';
import type { RequestHandler } from './$types';

export const POST: RequestHandler = async ({ request, fetch }) => {
  const body = await request.json();
  const target = `${env.BACKEND_API_URL ?? 'http://localhost:8000'}/deep-dive`;

  const response = await fetch(target, {
    method: 'POST',
    headers: { 'content-type': 'application/json' },
    body: JSON.stringify(body)
  });

  const payload = await response.text();

  return new Response(payload, {
    status: response.status,
    headers: { 'content-type': 'application/json' }
  });
};
