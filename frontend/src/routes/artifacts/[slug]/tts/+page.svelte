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

	let voices = $state<string[]>([]);
	let selectedVoice = $state('');
	let mode = $state<'summary' | 'full'>('full');
	let loadingVoices = $state(false);
	let statusMessage = $state('');
	let error = $state('');
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
			selectedVoice = (payload as VoicePayload).default_voice || voices[0] || selectedVoice || 'default';
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
		statusMessage = 'Generating or loading cached TTS audio...';
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
			statusMessage = 'Playback started.';
		} catch (err) {
			error = String(err);
			statusMessage = '';
		}
	}

	onMount(() => {
		void loadVoices();
	});
</script>

<main class="min-h-screen bg-gradient-to-b from-slate-50 via-cyan-50 to-amber-50 px-4 py-8 md:px-10">
	<div class="mx-auto flex w-full max-w-3xl flex-col gap-4">
		<header class="rounded-2xl border border-black/10 bg-white/85 p-5 shadow-sm">
			<p class="text-xs uppercase tracking-[0.18em] text-black/60">TTS Commentary</p>
			<h1 class="mt-1 text-3xl font-semibold">Audio Commentary Player</h1>
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
				<Button class="border-0 bg-emerald-700 text-white hover:bg-emerald-800" onclick={playAudio}>Play</Button>
				<Button variant="outline" onclick={stopAudio}>Stop</Button>
			</div>
			{#if statusMessage}
				<p class="mt-3 text-sm text-emerald-800">{statusMessage}</p>
			{/if}
			{#if error}
				<p class="mt-3 text-sm text-red-700">{error}</p>
			{/if}
			<audio bind:this={audioEl} controls class="mt-3 w-full"></audio>
		</section>
	</div>
</main>
