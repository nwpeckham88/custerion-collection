import { env } from '$env/dynamic/private';
import type { RequestHandler } from './$types';

export const GET: RequestHandler = async ({ fetch }) => {
  const target = `${env.BACKEND_API_URL ?? 'http://localhost:8000'}/health`;
  const response = await fetch(target);
  const payload = await response.json();

  return new Response(JSON.stringify(payload), {
    status: response.status,
    headers: { 'content-type': 'application/json' }
  });
};
