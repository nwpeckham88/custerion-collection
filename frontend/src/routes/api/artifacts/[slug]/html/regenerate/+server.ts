import { env } from '$env/dynamic/private';
import type { RequestHandler } from './$types';

export const POST: RequestHandler = async ({ params, fetch }) => {
  const slug = params.slug;
  const target = `${env.BACKEND_API_URL ?? 'http://localhost:8000'}/artifacts/${encodeURIComponent(slug)}/html/regenerate`;

  try {
    const response = await fetch(target, { method: 'POST' });
    const payload = await response.text();
    const contentType = response.headers.get('content-type') ?? 'application/json';

    return new Response(payload, {
      status: response.status,
      headers: { 'content-type': contentType }
    });
  } catch (error) {
    return new Response(
      JSON.stringify({ detail: `Backend HTML regenerate request failed: ${String(error)}` }),
      {
        status: 502,
        headers: { 'content-type': 'application/json' }
      }
    );
  }
};
