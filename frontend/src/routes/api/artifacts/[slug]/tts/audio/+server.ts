import { env } from '$env/dynamic/private';
import type { RequestHandler } from './$types';

export const GET: RequestHandler = async ({ params, url, fetch }) => {
  const slug = params.slug;
  const voice = url.searchParams.get('voice') ?? '';
  const mode = url.searchParams.get('mode') ?? 'full';
  const target = `${env.BACKEND_API_URL ?? 'http://localhost:8000'}/artifacts/${encodeURIComponent(slug)}/tts/audio?voice=${encodeURIComponent(voice)}&mode=${encodeURIComponent(mode)}`;

  try {
    const response = await fetch(target);
    const payload = await response.arrayBuffer();
    const contentType = response.headers.get('content-type') ?? 'audio/wav';

    return new Response(payload, {
      status: response.status,
      headers: { 'content-type': contentType }
    });
  } catch (error) {
    return new Response(
      JSON.stringify({ detail: `Backend TTS audio request failed: ${String(error)}` }),
      {
        status: 502,
        headers: { 'content-type': 'application/json' }
      }
    );
  }
};
