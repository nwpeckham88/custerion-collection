<script lang="ts">
	import { onMount, tick } from 'svelte';
	import { Badge } from '$lib/components/ui/badge';
	import { Button } from '$lib/components/ui/button';
	import * as Card from '$lib/components/ui/card';

	type ArtifactSummary = {
		title: string;
		slug: string;
		markdown_path: string | null;
		artifact_json_path: string | null;
		html_path: string | null;
		updated_at: string;
	};

	const introFlow = [
		{
			title: 'Configure Your Run',
			description: 'Pick a title, choose process mode, and decide whether to use dry-run or suggestion mode.'
		},
		{
			title: 'Generate and Monitor',
			description:
				'Start a run and follow live status updates including stage, progress, warnings, and diagnostics output.'
		},
		{
			title: 'Review Artifacts',
			description:
				'Browse saved markdown, JSON, and HTML reports, then open formatted deep-dives from the artifact list.'
		}
	] as const;

	let title = $state('The Red Shoes');
	let dryRun = $state(false);
	let suggest = $state(false);
	let processMode = $state<'hierarchical' | 'sequential'>('hierarchical');
	let loading = $state(false);
	let backendStatus = $state('checking...');
	let errorMessage = $state('');
	let diagnosticsPath = $state('');
	let runStatus = $state('');
	let runId = $state('');
	let runStage = $state('');
	let runProgress = $state(0);
	let resultMarkdown = $state('');
	let runWarnings = $state<string[]>([]);
	let runEvents = $state<string[]>([]);
	let runEventsPanel = $state<HTMLDivElement | null>(null);
	let artifacts = $state<ArtifactSummary[]>([]);
	let artifactsLoading = $state(false);
	let artifactsError = $state('');
	let regeneratingSlug = $state('');
	let artifactRegenerateErrors = $state<Record<string, string>>({});
	let showIntroFlow = $state(true);
	let currentIntroStep = $state(0);

	async function scrollRunEventsToBottom(): Promise<void> {
		if (!runEventsPanel || runEvents.length === 0) {
			return;
		}

		await tick();
		runEventsPanel.scrollTop = runEventsPanel.scrollHeight;
	}

	$effect(() => {
		runEvents.length;
		void scrollRunEventsToBottom();
	});

	onMount(async () => {
		try {
			const response = await fetch('/api/health');
			backendStatus = response.ok ? 'online' : `unhealthy (${response.status})`;
		} catch (error) {
			backendStatus = `offline (${String(error)})`;
		}

		await loadArtifacts();
	});

	function jumpTo(id: string): void {
		document.getElementById(id)?.scrollIntoView({ behavior: 'smooth', block: 'start' });
	}

	function nextIntroStep(): void {
		currentIntroStep = Math.min(introFlow.length - 1, currentIntroStep + 1);
	}

	function previousIntroStep(): void {
		currentIntroStep = Math.max(0, currentIntroStep - 1);
	}

	function finishIntroFlow(): void {
		showIntroFlow = false;
		jumpTo('run-deep-dive');
	}

	async function loadArtifacts(): Promise<void> {
		artifactsLoading = true;
		artifactsError = '';

		try {
			const response = await fetch('/api/artifacts?limit=12');
			const payload = await response.json();
			if (!response.ok) {
				throw new Error(payload?.detail ?? 'Artifact list request failed');
			}

			artifacts = Array.isArray(payload) ? payload : [];
		} catch (error) {
			artifactsError = String(error);
		} finally {
			artifactsLoading = false;
		}
	}

	async function regenerateArtifactHtml(slug: string): Promise<void> {
		regeneratingSlug = slug;
		artifactRegenerateErrors = { ...artifactRegenerateErrors, [slug]: '' };

		try {
			const response = await fetch(`/api/artifacts/${encodeURIComponent(slug)}/html/regenerate`, {
				method: 'POST'
			});
			const payload = await response.json();
			if (!response.ok) {
				throw new Error(payload?.detail ?? 'HTML regeneration failed');
			}

			await loadArtifacts();
		} catch (error) {
			artifactRegenerateErrors = {
				...artifactRegenerateErrors,
				[slug]: String(error)
			};
		} finally {
			regeneratingSlug = '';
		}
	}

	async function sleep(ms: number): Promise<void> {
		await new Promise((resolve) => setTimeout(resolve, ms));
	}

	async function pollRunStatus(activeRunId: string): Promise<void> {
		const maxPolls = 240;
		for (let poll = 0; poll < maxPolls; poll += 1) {
			const response = await fetch(`/api/deep-dive/${encodeURIComponent(activeRunId)}`);
			const payload = await response.json();
			if (!response.ok) {
				throw new Error(payload?.detail ?? 'Run status request failed');
			}

			runStatus = payload.status ?? runStatus;
			runStage = payload.stage ?? runStage;
			runProgress = Number(payload.progress ?? runProgress);
			runEvents = Array.isArray(payload.events) ? payload.events.map((entry: unknown) => String(entry)) : runEvents;

			if (payload.status === 'completed') {
				const result = payload.result ?? {};
				runStatus = result.status ?? 'success';
				diagnosticsPath = result.diagnostics_path ?? '';
				resultMarkdown = result.markdown ?? '';
				runWarnings = Array.isArray(result.warnings) ? result.warnings : [];
				return;
			}

			if (payload.status === 'failed') {
				throw new Error(payload.error ?? 'Deep-dive run failed');
			}

			await sleep(1250);
		}

		throw new Error('Deep-dive run timed out while polling for completion');
	}

	async function runDeepDive(): Promise<void> {
		loading = true;
		errorMessage = '';
		runStatus = '';
		runId = '';
		runStage = '';
		runProgress = 0;
		diagnosticsPath = '';
		resultMarkdown = '';
		runWarnings = [];
		runEvents = [];

		try {
			const startResponse = await fetch('/api/deep-dive/start', {
				method: 'POST',
				headers: { 'content-type': 'application/json' },
				body: JSON.stringify({
					title: title.trim() || null,
					suggest,
					process_mode: processMode,
					dry_run: dryRun
				})
			});

			const startPayload = await startResponse.json();
			if (!startResponse.ok) {
				throw new Error(startPayload?.detail ?? 'Run start failed');
			}

			runId = String(startPayload.run_id ?? '');
			runStatus = String(startPayload.status ?? 'queued');
			runStage = String(startPayload.stage ?? 'Queued');
			runProgress = Number(startPayload.progress ?? 0);
			runEvents = ['System: Run queued'];

			if (!runId) {
				throw new Error('Run start response missing run ID');
			}

			await pollRunStatus(runId);
			if (runStatus === 'failed' || !resultMarkdown) {
				throw new Error('Run completed without usable markdown output');
			}

			await loadArtifacts();
		} catch (error) {
			errorMessage = String(error);
		} finally {
			loading = false;
		}
	}
</script>

<main class="relative overflow-hidden px-5 py-8 md:px-10 md:py-12">
	<div class="mx-auto flex w-full max-w-6xl flex-col gap-6">
		<section class="hero-shell rounded-3xl border border-black/10 p-6 shadow-xl md:p-10">
			<div class="flex flex-wrap items-start justify-between gap-4">
				<Badge class="border-0 bg-black text-white">Custerion Collection</Badge>
				<div class="inline-flex h-fit items-center gap-2 rounded-full border border-black/10 bg-white/85 px-3 py-1 text-sm">
					<span class="h-2 w-2 rounded-full {backendStatus === 'online' ? 'bg-green-500' : 'bg-red-500'}"></span>
					Backend: {backendStatus}
				</div>
			</div>

			<div class="mt-5 grid gap-5 md:grid-cols-[1.25fr_0.75fr] md:items-end">
				<div class="space-y-4">
					<h1 class="max-w-3xl text-4xl font-bold leading-tight text-balance md:text-6xl">
						From one title to a cinematic deep-dive.
					</h1>
					<p class="max-w-xl text-base text-black/75 md:text-lg">
						Run the crew, watch the agent conversation, open the finished report.
					</p>
					<div class="flex flex-wrap gap-2">
						<Button class="border-0 bg-black text-white hover:bg-black/90" onclick={() => jumpTo('run-deep-dive')}
							>Start a Run</Button
						>
						<Button variant="outline" onclick={() => (showIntroFlow = true)}>Open Intro Flow</Button>
					</div>
				</div>

				<div class="hero-metrics grid gap-2 rounded-2xl border border-black/10 bg-white/70 p-3 text-sm backdrop-blur">
					<div class="metric-row">
						<span>Mode</span>
						<strong>{processMode}</strong>
					</div>
					<div class="metric-row">
						<span>Dry run</span>
						<strong>{dryRun ? 'On' : 'Off'}</strong>
					</div>
					<div class="metric-row">
						<span>Artifacts</span>
						<strong>{artifacts.length}</strong>
					</div>
				</div>
			</div>
		</section>

		<section id="run-deep-dive" class="space-y-5 rounded-3xl border border-black/5 bg-white/85 p-6 shadow-lg backdrop-blur md:p-8">
			<h2 class="text-3xl font-bold">Run Deep Dive</h2>
			<p class="text-sm text-muted-foreground">
				Step-by-step: choose title and mode, click Generate, then check status and saved artifacts.
			</p>

			<div class="grid gap-4 md:grid-cols-2">
				<label class="space-y-2 text-sm">
					<span class="font-medium">Film title</span>
					<input
						class="w-full rounded-xl border border-black/10 bg-white px-3 py-2 outline-none focus:ring-2 focus:ring-primary"
						bind:value={title}
						placeholder="e.g., The Red Shoes"
					/>
				</label>

				<label class="space-y-2 text-sm">
					<span class="font-medium">Process mode</span>
					<select
						class="w-full rounded-xl border border-black/10 bg-white px-3 py-2 outline-none focus:ring-2 focus:ring-primary"
						bind:value={processMode}
					>
						<option value="hierarchical">hierarchical</option>
						<option value="sequential">sequential</option>
					</select>
				</label>
			</div>

			<div class="flex flex-wrap items-center gap-4 text-sm">
				<label class="inline-flex items-center gap-2">
					<input type="checkbox" bind:checked={dryRun} />
					Dry run (fast smoke output)
				</label>
				<label class="inline-flex items-center gap-2">
					<input type="checkbox" bind:checked={suggest} />
					Suggest mode (no title required)
				</label>
			</div>

			<div class="flex flex-wrap gap-3">
				<Button class="preset-filled-primary-500 border-0" onclick={runDeepDive} disabled={loading}>
					{loading ? 'Running...' : 'Generate'}
				</Button>
				<Button
					variant="outline"
					onclick={async () => {
						await loadArtifacts();
						jumpTo('saved-artifacts');
					}}
				>
					Refresh Artifact List
				</Button>
			</div>

			{#if errorMessage}
				<div class="preset-filled-error-500 rounded-xl px-4 py-3 text-sm">{errorMessage}</div>
			{/if}

			{#if runStatus}
				<div class="rounded-xl border border-black/10 bg-white p-4 text-sm">
					{#if runId}
						<div><span class="font-semibold">Run ID:</span> <code>{runId}</code></div>
					{/if}
					<div><span class="font-semibold">Status:</span> {runStatus}</div>
					{#if runStage}
						<div class="mt-1"><span class="font-semibold">Stage:</span> {runStage}</div>
					{/if}
					<div class="mt-1"><span class="font-semibold">Progress:</span> {runProgress}%</div>
					<div class="mt-1"><span class="font-semibold">Diagnostics:</span> {diagnosticsPath}</div>
					{#if runEvents.length > 0}
						<div class="mt-3">
							<div class="font-semibold">Agent Conversation</div>
							<div
								class="mt-2 max-h-56 overflow-auto rounded-lg border border-black/10 bg-neutral-50 px-3 py-2 font-mono text-xs leading-relaxed"
								bind:this={runEventsPanel}
							>
								{#each runEvents as event}
									<div>{event}</div>
								{/each}
							</div>
						</div>
					{/if}
				</div>
			{/if}

			{#if runWarnings.length > 0}
				<div class="rounded-xl border border-amber-300 bg-amber-50 px-4 py-3 text-sm text-amber-900">
					<div class="font-semibold">Warnings</div>
					<ul class="mt-2 list-disc space-y-1 pl-5">
						{#each runWarnings as warning}
							<li>{warning}</li>
						{/each}
					</ul>
				</div>
			{/if}

			{#if resultMarkdown}
				<div class="max-h-96 overflow-auto rounded-xl border border-black/10 bg-white p-4">
					<pre class="text-sm whitespace-pre-wrap">{resultMarkdown}</pre>
				</div>
			{/if}

			<div id="saved-artifacts" class="space-y-3 rounded-xl border border-black/10 bg-white p-4">
				<div class="flex items-center justify-between">
					<h3 class="text-lg font-semibold">Saved Artifacts</h3>
					<Button variant="outline" onclick={loadArtifacts} disabled={artifactsLoading}>
						{artifactsLoading ? 'Refreshing...' : 'Refresh'}
					</Button>
				</div>

				{#if artifactsError}
					<div class="rounded-lg border border-red-300 bg-red-50 px-3 py-2 text-sm text-red-900">{artifactsError}</div>
				{:else if artifacts.length === 0}
					<div class="text-sm text-muted-foreground">No artifacts yet. Run a deep dive to generate one.</div>
				{:else}
					<ul class="space-y-2 text-sm">
						{#each artifacts as artifact}
							<li class="rounded-lg border border-black/10 px-3 py-2 md:px-4 md:py-3">
								<div class="flex flex-wrap items-center justify-between gap-2">
									<div class="font-medium">{artifact.title}</div>
									<div class="text-xs text-muted-foreground">{artifact.updated_at}</div>
								</div>
								{#if artifact.markdown_path}
									<div class="mt-1 text-xs break-all">Markdown: <code>{artifact.markdown_path}</code></div>
								{/if}
								{#if artifact.artifact_json_path}
									<div class="text-xs break-all">JSON: <code>{artifact.artifact_json_path}</code></div>
								{/if}
								{#if artifact.html_path}
									<div class="mt-2 text-xs">
										<a
											href={`/api/artifacts/${artifact.slug}/html`}
											target="_blank"
											rel="noopener noreferrer"
											class="underline decoration-dotted underline-offset-2"
										>
											Open formatted report
										</a>
									</div>
								{/if}
								<div class="mt-2 flex flex-wrap items-center gap-2">
									<Button
										variant="outline"
										size="sm"
										onclick={() => regenerateArtifactHtml(artifact.slug)}
										disabled={regeneratingSlug === artifact.slug}
									>
										{#if regeneratingSlug === artifact.slug}
											Regenerating...
										{:else if artifactRegenerateErrors[artifact.slug]}
											Retry Regenerate
										{:else}
											Regenerate HTML
										{/if}
									</Button>
								</div>
								{#if artifactRegenerateErrors[artifact.slug]}
									<div class="mt-1 text-xs text-red-700 break-all">{artifactRegenerateErrors[artifact.slug]}</div>
								{/if}
							</li>
						{/each}
					</ul>
				{/if}
			</div>
		</section>
	</div>

	{#if showIntroFlow}
		<div class="intro-overlay fixed inset-0 z-50 flex items-center justify-center p-4">
			<div class="intro-atmosphere absolute inset-0" aria-hidden="true"></div>
			<Card.Root class="intro-modal relative w-full max-w-2xl border-0 shadow-2xl">
				<Card.Header class="space-y-3">
					<div class="flex items-center justify-between gap-3">
						<Badge class="border-0 bg-black text-white">Intro Flow</Badge>
						<div class="text-xs text-muted-foreground">Step {currentIntroStep + 1} of {introFlow.length}</div>
					</div>
					<Card.Title class="text-3xl leading-tight tracking-tight md:text-4xl">{introFlow[currentIntroStep].title}</Card.Title>
					<Card.Description class="text-sm md:text-base">
						{introFlow[currentIntroStep].description}
					</Card.Description>
				</Card.Header>
				<Card.Content class="space-y-5">
					<div class="h-2 w-full overflow-hidden rounded-full bg-black/10">
						<div
							class="h-full rounded-full bg-gradient-to-r from-amber-500 via-orange-500 to-rose-500 transition-all duration-500"
							style={`width: ${((currentIntroStep + 1) / introFlow.length) * 100}%`}
						></div>
					</div>

					<div class="rounded-xl border border-black/10 bg-white/70 p-3 text-xs uppercase tracking-[0.16em] text-muted-foreground">
						Guided onboarding to get you from setup to your first deep-dive artifact.
					</div>

					<div class="flex flex-wrap justify-between gap-2">
						<Button variant="ghost" class="text-black/70 hover:text-black" onclick={() => (showIntroFlow = false)}
							>Skip Intro</Button
						>
						<div class="flex gap-2">
							<Button variant="outline" class="border-black/20" onclick={previousIntroStep} disabled={currentIntroStep === 0}
								>Back</Button
							>
							{#if currentIntroStep < introFlow.length - 1}
								<Button class="border-0 bg-black text-white hover:bg-black/90" onclick={nextIntroStep}>Next</Button>
							{:else}
								<Button class="border-0 bg-emerald-700 text-white hover:bg-emerald-800" onclick={finishIntroFlow}
									>Start Exploring</Button
								>
							{/if}
						</div>
					</div>
				</Card.Content>
			</Card.Root>
		</div>
	{/if}
</main>

<style>
	.hero-shell {
		background:
			radial-gradient(circle at 8% 12%, rgba(255, 198, 116, 0.35), transparent 42%),
			radial-gradient(circle at 92% 20%, rgba(220, 90, 66, 0.24), transparent 38%),
			linear-gradient(158deg, rgba(255, 255, 255, 0.92), rgba(247, 241, 232, 0.9));
		backdrop-filter: blur(8px);
	}

	.metric-row {
		display: flex;
		justify-content: space-between;
		gap: 12px;
		padding: 6px 4px;
		border-bottom: 1px solid rgba(0, 0, 0, 0.08);
	}

	.metric-row:last-child {
		border-bottom: 0;
	}

	.intro-overlay {
		background: color-mix(in oklch, black 45%, transparent);
		backdrop-filter: blur(6px);
	}

	.intro-atmosphere {
		background:
			radial-gradient(circle at 14% 20%, rgba(255, 190, 92, 0.28), transparent 44%),
			radial-gradient(circle at 82% 16%, rgba(212, 67, 41, 0.24), transparent 42%),
			radial-gradient(circle at 50% 92%, rgba(42, 53, 72, 0.24), transparent 48%);
	}

	.intro-modal {
		background: linear-gradient(160deg, rgba(255, 255, 255, 0.95), rgba(249, 245, 236, 0.96));
		animation: intro-rise 220ms ease-out;
	}

	@keyframes intro-rise {
		from {
			opacity: 0;
			transform: translateY(10px) scale(0.985);
		}
		to {
			opacity: 1;
			transform: translateY(0) scale(1);
		}
	}
</style>
