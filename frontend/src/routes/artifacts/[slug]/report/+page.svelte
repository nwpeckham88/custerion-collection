<script lang="ts">
	import { onMount } from 'svelte';
	import { page } from '$app/state';
	import { Button } from '$lib/components/ui/button';

	type VoicePayload = {
		slug: string;
		model: string;
		default_voice: string;
		voices: string[];
	};

	const slug = $derived(page.params.slug ?? '');
	const reportSrc = $derived(`/api/artifacts/${encodeURIComponent(slug)}/html`);

	let voices = $state<string[]>([]);
	let selectedVoice = $state('');
	let mode = $state<'summary' | 'full'>('full');
	let runtimeLabel = $state('');
	let statusMessage = $state('');
	let error = $state('');
	let loadingVoices = $state(false);
	let audioEl = $state<HTMLAudioElement | null>(null);

	async function loadVoices(): Promise<void> {
		loadingVoices = true;
		error = '';
		try {
			const response = await fetch(`/api/artifacts/${encodeURIComponent(slug)}/tts/voices`);
			const payload = (await response.json()) as VoicePayload | { detail?: string };
			if (!response.ok) {
				throw new Error((payload as { detail?: string }).detail ?? 'TTS voices unavailable');
			}
			voices = Array.isArray((payload as VoicePayload).voices) ? (payload as VoicePayload).voices : [];
			selectedVoice =
				(payload as VoicePayload).default_voice || voices[0] || selectedVoice || 'default';
			runtimeLabel = (payload as VoicePayload).model;
		} catch (err) {
			error = String(err);
		} finally {
			loadingVoices = false;
		}
	}

	function stopAudio(): void {
		if (!audioEl) {
			return;
		}
		audioEl.pause();
		audioEl.currentTime = 0;
	}

	async function playAudio(): Promise<void> {
		statusMessage = 'Preparing narration...';
		error = '';

		const voice = selectedVoice || 'default';
		const src = `/api/artifacts/${encodeURIComponent(slug)}/tts/audio?voice=${encodeURIComponent(voice)}&mode=${encodeURIComponent(mode)}`;

		if (!audioEl) {
			statusMessage = '';
			return;
		}

		audioEl.src = src;
		try {
			await audioEl.play();
			statusMessage = `Now reading ${mode === 'summary' ? 'the summary' : 'the full report'}.`;
		} catch (err) {
			error = String(err);
			statusMessage = '';
		}
	}

	onMount(() => {
		void loadVoices();
	});
</script>

<main class="min-h-screen bg-gradient-to-br from-amber-50 via-lime-50 to-teal-50 px-4 py-8 md:px-8">
	<div class="mx-auto flex w-full max-w-7xl flex-col gap-4">
		<header class="rounded-2xl border border-black/10 bg-white/80 p-5 shadow-sm backdrop-blur">
			<p class="text-xs uppercase tracking-[0.18em] text-black/60">Artifact Report</p>
			<h1 class="mt-1 text-3xl font-semibold">Report Reader</h1>
			<p class="mt-2 text-sm text-black/70">
				Read the full HTML report and optionally play generated narration.
			</p>
		</header>

		<section class="rounded-2xl border border-black/10 bg-white/85 p-5 shadow-sm">
			<div class="flex flex-wrap items-end gap-2">
				<label class="grid gap-1 text-sm">
					<span class="text-xs uppercase tracking-[0.14em] text-black/65">Voice</span>
					<select
						bind:value={selectedVoice}
						disabled={loadingVoices || voices.length === 0}
						class="rounded-md border border-black/15 bg-white px-2 py-1"
					>
						{#if voices.length === 0}
							<option value="default">default</option>
						{:else}
							{#each voices as voice}
								<option value={voice}>{voice}</option>
							{/each}
						{/if}
					</select>
				</label>

				<label class="grid gap-1 text-sm">
					<span class="text-xs uppercase tracking-[0.14em] text-black/65">Read Mode</span>
					<select bind:value={mode} class="rounded-md border border-black/15 bg-white px-2 py-1">
						<option value="full">Full report</option>
						<option value="summary">Summary only</option>
					</select>
				</label>

				<Button class="border-0 bg-emerald-700 text-white hover:bg-emerald-800" onclick={playAudio}>Play narration</Button>
				<Button variant="outline" onclick={stopAudio}>Stop</Button>
				<Button variant="outline" onclick={loadVoices}>Reload voices</Button>
			</div>

			{#if runtimeLabel}
				<p class="mt-3 text-xs text-black/60">TTS runtime: {runtimeLabel}</p>
			{/if}
			{#if statusMessage}
				<p class="mt-2 text-sm text-emerald-800">{statusMessage}</p>
			{/if}
			{#if error}
				<p class="mt-2 text-sm text-red-700">{error}</p>
			{/if}

			<audio bind:this={audioEl} controls class="mt-3 w-full"></audio>
		</section>

		<section class="overflow-hidden rounded-2xl border border-black/10 bg-white shadow-sm">
			<iframe title="Generated report" src={reportSrc} class="h-[70vh] w-full border-0"></iframe>
		</section>
	</div>
</main>
