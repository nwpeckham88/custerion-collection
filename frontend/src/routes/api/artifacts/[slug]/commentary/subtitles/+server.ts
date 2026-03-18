import { env } from '$env/dynamic/private';
import type { RequestHandler } from './$types';

export const POST: RequestHandler = async ({ params, fetch, request }) => {
  const slug = params.slug;
  const target = `${env.BACKEND_API_URL ?? 'http://localhost:8000'}/artifacts/${encodeURIComponent(slug)}/commentary/subtitles`;

  try {
    const body = await request.text();
    const response = await fetch(target, {
      method: 'POST',
      headers: { 'content-type': 'application/json' },
      body
    });
    const payload = await response.text();
    const contentType = response.headers.get('content-type') ?? 'application/json';

    return new Response(payload, {
      status: response.status,
      headers: { 'content-type': contentType }
    });
  } catch (error) {
    return new Response(
      JSON.stringify({ detail: `Backend subtitle import request failed: ${String(error)}` }),
      {
        status: 502,
        headers: { 'content-type': 'application/json' }
      }
    );
  }
};
