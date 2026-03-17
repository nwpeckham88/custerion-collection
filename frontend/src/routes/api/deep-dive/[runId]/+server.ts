import { env } from '$env/dynamic/private';
import type { RequestHandler } from './$types';

export const GET: RequestHandler = async ({ params, fetch }) => {
  const runId = params.runId;
  const target = `${env.BACKEND_API_URL ?? 'http://localhost:8000'}/deep-dive/${encodeURIComponent(runId)}`;

  try {
    const response = await fetch(target);
    const payload = await response.text();
    const contentType = response.headers.get('content-type') ?? 'application/json';

    return new Response(payload, {
      status: response.status,
      headers: { 'content-type': contentType }
    });
  } catch (error) {
    return new Response(JSON.stringify({ detail: `Backend deep-dive status failed: ${String(error)}` }), {
      status: 502,
      headers: { 'content-type': 'application/json' }
    });
  }
};
