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

	type VoicePayload = {
		slug: string;
		model: string;
		default_voice: string;
		voices: string[];
	};

	const slug = $derived(page.params.slug ?? '');
	let loading = $state(true);
	let error = $state('');
	let payload = $state<CommentaryPayload | null>(null);
	let positionMs = $state(0);
	let isPlaying = $state(false);
	let playbackRate = $state(1);
	let realtimePreview = $state<Segment[]>([]);
	let subtitleText = $state('');
	let subtitleImportState = $state('');
	let subtitleImportError = $state('');
	let ttsVoices = $state<string[]>([]);
	let ttsVoice = $state('');
	let ttsMode = $state<'summary' | 'full'>('summary');
	let ttsRuntime = $state('');
	let ttsLoading = $state(false);
	let ttsError = $state('');
	let ttsStatus = $state('');
	let ttsAudio = $state<HTMLAudioElement | null>(null);

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

	async function loadTtsVoices(): Promise<void> {
		ttsLoading = true;
		ttsError = '';

		try {
			const response = await fetch(`/api/artifacts/${encodeURIComponent(slug)}/tts/voices`);
			const data = (await response.json()) as VoicePayload | { detail?: string };
			if (!response.ok) {
				throw new Error((data as { detail?: string }).detail ?? 'TTS voices unavailable');
			}

			ttsVoices = Array.isArray((data as VoicePayload).voices) ? (data as VoicePayload).voices : [];
			ttsVoice = (data as VoicePayload).default_voice || ttsVoices[0] || ttsVoice || 'default';
			ttsRuntime = (data as VoicePayload).model;
		} catch (err) {
			ttsError = String(err);
		} finally {
			ttsLoading = false;
		}
	}

	async function playTts(): Promise<void> {
		ttsStatus = 'Generating narration...';
		ttsError = '';

		if (!ttsAudio) {
			ttsStatus = '';
			return;
		}

		const voice = ttsVoice || 'default';
		ttsAudio.src = `/api/artifacts/${encodeURIComponent(slug)}/tts/audio?voice=${encodeURIComponent(voice)}&mode=${encodeURIComponent(ttsMode)}`;

		try {
			await ttsAudio.play();
			ttsStatus = 'TTS playback started.';
		} catch (err) {
			ttsError = String(err);
			ttsStatus = '';
		}
	}

	function stopTts(): void {
		if (!ttsAudio) {
			return;
		}
		ttsAudio.pause();
		ttsAudio.currentTime = 0;
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

	async function importSubtitleText(): Promise<void> {
		subtitleImportState = 'Importing subtitles...';
		subtitleImportError = '';

		try {
			const response = await fetch(`/api/artifacts/${encodeURIComponent(slug)}/commentary/subtitles`, {
				method: 'POST',
				headers: { 'content-type': 'application/json' },
				body: JSON.stringify({ subtitle_text: subtitleText })
			});
			const data = await response.json();
			if (!response.ok) {
				throw new Error(data?.detail ?? 'Subtitle import failed');
			}

			subtitleImportState = `Imported ${data.segment_count} subtitle cues.`;
			await loadCommentary();
		} catch (err) {
			subtitleImportError = String(err);
			subtitleImportState = '';
		}
	}

	async function importSubtitleFile(event: Event): Promise<void> {
		const target = event.currentTarget as HTMLInputElement;
		const file = target.files?.[0];
		if (!file) {
			return;
		}

		subtitleText = await file.text();
		await importSubtitleText();
		target.value = '';
	}

	onMount(() => {
		void loadCommentary();
		void loadTtsVoices();
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
			<section class="rounded-2xl border border-black/10 bg-white/85 p-5 shadow-sm">
				<h2 class="text-xl font-semibold">TTS Narration</h2>
				<p class="mt-2 text-sm text-black/70">Play audio narration for the current film report while you follow the timeline commentary.</p>
				<div class="mt-3 flex flex-wrap items-end gap-2">
					<label class="grid gap-1 text-sm">
						<span class="text-xs uppercase tracking-[0.14em] text-black/65">Voice</span>
						<select bind:value={ttsVoice} disabled={ttsLoading || ttsVoices.length === 0} class="rounded-md border border-black/15 bg-white px-2 py-1">
							{#if ttsVoices.length === 0}
								<option value="default">default</option>
							{:else}
								{#each ttsVoices as voice}
									<option value={voice}>{voice}</option>
								{/each}
							{/if}
						</select>
					</label>
					<label class="grid gap-1 text-sm">
						<span class="text-xs uppercase tracking-[0.14em] text-black/65">Read Mode</span>
						<select bind:value={ttsMode} class="rounded-md border border-black/15 bg-white px-2 py-1">
							<option value="summary">Summary</option>
							<option value="full">Full report</option>
						</select>
					</label>
					<Button class="border-0 bg-emerald-700 text-white hover:bg-emerald-800" onclick={playTts}>Play narration</Button>
					<Button variant="outline" onclick={stopTts}>Stop</Button>
					<Button variant="outline" onclick={loadTtsVoices} disabled={ttsLoading}>
						{ttsLoading ? 'Loading...' : 'Reload voices'}
					</Button>
				</div>
				{#if ttsRuntime}
					<p class="mt-2 text-xs text-black/60">Runtime: {ttsRuntime}</p>
				{/if}
				{#if ttsStatus}
					<p class="mt-2 text-sm text-emerald-800">{ttsStatus}</p>
				{/if}
				{#if ttsError}
					<p class="mt-2 text-sm text-red-700">{ttsError}</p>
				{/if}
				<audio bind:this={ttsAudio} controls class="mt-3 w-full"></audio>
			</section>

			<section class="rounded-2xl border border-black/10 bg-white/85 p-5 shadow-sm">
				<h2 class="text-xl font-semibold">Subtitle Import (SRT)</h2>
				<p class="mt-2 text-sm text-black/70">
					Use any `.srt` file. The app will run a smart planner that aligns report insights to subtitle-timed beats.
				</p>
				<div class="mt-3 flex flex-wrap items-center gap-2">
					<input
						type="file"
						accept=".srt,text/plain"
						onchange={importSubtitleFile}
						class="block text-sm"
					/>
					<Button variant="outline" onclick={importSubtitleText} disabled={!subtitleText.trim()}>
						Import pasted SRT
					</Button>
				</div>
				<textarea
					bind:value={subtitleText}
					rows="6"
					placeholder="Paste SRT here..."
					class="mt-3 w-full rounded-lg border border-black/15 bg-white p-3 text-sm"
				></textarea>
				{#if subtitleImportState}
					<p class="mt-2 text-sm text-emerald-800">{subtitleImportState}</p>
				{/if}
				{#if subtitleImportError}
					<p class="mt-2 text-sm text-red-700">{subtitleImportError}</p>
				{/if}
			</section>

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
