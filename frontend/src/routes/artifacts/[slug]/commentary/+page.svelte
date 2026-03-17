<script lang="ts">
	import { onMount } from 'svelte';
	import { page } from '$app/state';
	import { Button } from '$lib/components/ui/button';

	type Segment = {
		order_index: number;
		timestamp_ms: number | null;
		scene_label: string;
		commentary: string;
		source: string | null;
		confidence: number;
	};

	type CommentaryPayload = {
		slug: string;
		title: string;
		commentary_mode: string;
		duration_ms: number;
		segments: Segment[];
		external_playback: {
			provider: string;
			itemId: string | null;
			positionMs: number | null;
		};
	};

	const slug = $derived(page.params.slug ?? '');
	let loading = $state(true);
	let error = $state('');
	let payload = $state<CommentaryPayload | null>(null);
	let positionMs = $state(0);
	let isPlaying = $state(false);
	let playbackRate = $state(1);
	let realtimePreview = $state<Segment[]>([]);

	let timer: ReturnType<typeof setInterval> | null = null;

	const durationMs = $derived(payload?.duration_ms ?? 0);
	const timedSegments = $derived((payload?.segments ?? []).filter((seg) => seg.timestamp_ms !== null));
	const isSeekEnabled = $derived(timedSegments.length > 0 && durationMs > 0);
	const activeIndex = $derived.by(() => {
		const segments = payload?.segments ?? [];
		let current = 0;
		for (let i = 0; i < segments.length; i += 1) {
			const ts = segments[i].timestamp_ms;
			if (ts !== null && ts <= positionMs) {
				current = i;
			}
		}
		return current;
	});

	function formatTime(ms: number | null): string {
		if (ms === null) {
			return 'Untimed';
		}
		const totalSeconds = Math.floor(ms / 1000);
		const hours = Math.floor(totalSeconds / 3600);
		const minutes = Math.floor((totalSeconds % 3600) / 60);
		const seconds = totalSeconds % 60;
		if (hours > 0) {
			return `${String(hours).padStart(2, '0')}:${String(minutes).padStart(2, '0')}:${String(seconds).padStart(2, '0')}`;
		}
		return `${String(minutes).padStart(2, '0')}:${String(seconds).padStart(2, '0')}`;
	}

	function seekTo(ms: number): void {
		positionMs = Math.max(0, Math.min(ms, durationMs || ms));
	}

	function togglePlayback(): void {
		isPlaying = !isPlaying;
	}

	async function loadCommentary(): Promise<void> {
		loading = true;
		error = '';
		try {
			const response = await fetch(`/api/artifacts/${encodeURIComponent(slug)}/commentary`);
			const data = await response.json();
			if (!response.ok) {
				throw new Error(data?.detail ?? 'Commentary request failed');
			}
			payload = data;
			positionMs = 0;
		} catch (err) {
			error = String(err);
		} finally {
			loading = false;
		}
	}

	async function refreshRealtimePreview(): Promise<void> {
		if (!payload) {
			return;
		}
		try {
			const response = await fetch(
				`/api/artifacts/${encodeURIComponent(slug)}/commentary/realtime?position_ms=${positionMs}&window_ms=30000&limit=4`
			);
			const data = await response.json();
			if (response.ok) {
				realtimePreview = Array.isArray(data.upcoming_segments) ? data.upcoming_segments : [];
			}
		} catch {
			realtimePreview = [];
		}
	}

	onMount(() => {
		void loadCommentary();
	});

	$effect(() => {
		if (timer) {
			clearInterval(timer);
			timer = null;
		}
		if (!isPlaying || !payload) {
			return;
		}
		timer = setInterval(() => {
			positionMs = Math.min(positionMs + 1000 * playbackRate, durationMs || Number.MAX_SAFE_INTEGER);
			if (durationMs > 0 && positionMs >= durationMs) {
				isPlaying = false;
			}
		}, 1000);

		return () => {
			if (timer) {
				clearInterval(timer);
				timer = null;
			}
		};
	});

	$effect(() => {
		positionMs;
		void refreshRealtimePreview();
	});
</script>

<main class="commentary-page min-h-screen px-4 py-8 md:px-10">
	<div class="mx-auto flex w-full max-w-6xl flex-col gap-4">
		<div class="rounded-3xl border border-black/15 bg-white/75 p-6 shadow-xl backdrop-blur">
			<p class="text-xs uppercase tracking-[0.18em] text-black/60">Guided Commentary</p>
			<h1 class="mt-2 text-4xl font-bold leading-tight md:text-5xl">{payload?.title ?? 'Loading movie commentary'}</h1>
			<p class="mt-2 text-sm text-black/70">
				Seek through the timeline and follow scene-level commentary in real time.
			</p>
		</div>

		{#if loading}
			<div class="rounded-2xl border border-black/10 bg-white/80 p-4">Loading commentary timeline...</div>
		{:else if error}
			<div class="rounded-2xl border border-red-300 bg-red-50 p-4 text-red-900">{error}</div>
		{:else if payload}
			<div class="grid gap-4 md:grid-cols-[1.15fr_0.85fr]">
				<section class="rounded-2xl border border-black/10 bg-white/85 p-5 shadow-sm">
					<div class="flex flex-wrap items-center gap-2 text-xs text-black/65">
						<span>Mode: {payload.commentary_mode}</span>
						<span>Duration: {formatTime(durationMs)}</span>
						<span>Provider hook: {payload.external_playback.provider}</span>
					</div>

					<div class="mt-4 space-y-3">
						<label for="timeline-seek" class="text-sm font-medium">Timeline Seek</label>
						<input
							id="timeline-seek"
							type="range"
							min="0"
							max={Math.max(durationMs, 1)}
							step="1000"
							bind:value={positionMs}
							disabled={!isSeekEnabled}
							class="w-full accent-emerald-700"
						/>
						<div class="flex items-center justify-between text-xs text-black/60">
							<span>{formatTime(positionMs)}</span>
							<span>{isSeekEnabled ? formatTime(durationMs) : 'Untimed only'}</span>
						</div>
					</div>

					<div class="mt-4 flex flex-wrap gap-2">
						<Button class="border-0 bg-emerald-700 text-white hover:bg-emerald-800" onclick={togglePlayback}>
							{isPlaying ? 'Pause' : 'Play'}
						</Button>
						<Button variant="outline" onclick={() => seekTo(0)}>Reset</Button>
						<Button variant="outline" onclick={() => (playbackRate = playbackRate === 1 ? 1.5 : 1)}>
							Speed {playbackRate}x
						</Button>
					</div>

					{#if !isSeekEnabled}
						<p class="mt-3 rounded-lg border border-amber-300 bg-amber-50 px-3 py-2 text-xs text-amber-900">
							Timestamped transcript lines were not found. Showing untimed guided commentary.
						</p>
					{/if}
				</section>

				<section class="rounded-2xl border border-black/10 bg-white/85 p-5 shadow-sm">
					<h2 class="text-xl font-semibold">Realtime Preview</h2>
					{#if realtimePreview.length === 0}
						<p class="mt-2 text-sm text-black/70">No upcoming timestamped segments in the current 30s window.</p>
					{:else}
						<ul class="mt-3 space-y-2 text-sm">
							{#each realtimePreview as seg}
								<li class="rounded-lg border border-black/10 bg-white/80 p-2">
									<span class="font-mono text-xs text-black/60">{formatTime(seg.timestamp_ms)}</span>
									<p class="font-medium">{seg.scene_label}</p>
								</li>
							{/each}
						</ul>
					{/if}
				</section>
			</div>

			<section class="rounded-2xl border border-black/10 bg-white/90 p-5 shadow-sm">
				<h2 class="text-2xl font-semibold">Transcript</h2>
				<ul class="mt-4 space-y-2">
					{#each payload.segments as segment, idx}
						<li class="rounded-xl border px-3 py-3 transition-colors {idx === activeIndex ? 'border-emerald-600 bg-emerald-50' : 'border-black/10 bg-white'}">
							<button
								type="button"
								class="w-full text-left"
								onclick={() => segment.timestamp_ms !== null && seekTo(segment.timestamp_ms)}
								disabled={segment.timestamp_ms === null}
							>
								<div class="flex flex-wrap items-center justify-between gap-2">
									<span class="font-mono text-xs text-black/70">{formatTime(segment.timestamp_ms)}</span>
									<span class="text-xs text-black/60">Confidence {(segment.confidence * 100).toFixed(0)}%</span>
								</div>
								<p class="mt-1 font-semibold">{segment.scene_label}</p>
								<p class="mt-1 text-sm text-black/75">{segment.commentary}</p>
							</button>
						</li>
					{/each}
				</ul>
			</section>
		{/if}
	</div>
</main>

<style>
	.commentary-page {
		background:
			radial-gradient(circle at 15% 10%, rgba(232, 172, 90, 0.24), transparent 38%),
			radial-gradient(circle at 88% 22%, rgba(71, 124, 108, 0.22), transparent 42%),
			linear-gradient(160deg, rgba(245, 240, 231, 0.92), rgba(231, 239, 243, 0.94));
	}
</style>
