<script lang="ts">
	import { onMount } from 'svelte';
	import { Badge } from '$lib/components/ui/badge';
	import { Button } from '$lib/components/ui/button';
	import * as Card from '$lib/components/ui/card';
	import { Dialog } from 'bits-ui';
	import { Progress } from '@skeletonlabs/skeleton-svelte';

	const focusAreas = [
		{ label: 'Artifact Pipeline', score: '92%' },
		{ label: 'Identity Consistency', score: '88%' },
		{ label: 'Live Test Guardrails', score: '79%' }
	];

	type ArtifactSummary = {
		title: string;
		slug: string;
		markdown_path: string | null;
		artifact_json_path: string | null;
		updated_at: string;
	};

	let title = $state('The Red Shoes');
	let dryRun = $state(true);
	let suggest = $state(false);
	let processMode = $state<'hierarchical' | 'sequential'>('hierarchical');
	let loading = $state(false);
	let backendStatus = $state('checking...');
	let errorMessage = $state('');
	let diagnosticsPath = $state('');
	let runStatus = $state('');
	let resultMarkdown = $state('');
	let runWarnings = $state<string[]>([]);
	let artifacts = $state<ArtifactSummary[]>([]);
	let artifactsLoading = $state(false);
	let artifactsError = $state('');

	onMount(async () => {
		try {
			const response = await fetch('/api/health');
			backendStatus = response.ok ? 'online' : `unhealthy (${response.status})`;
		} catch (error) {
			backendStatus = `offline (${String(error)})`;
		}

		await loadArtifacts();
	});

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

	async function runDeepDive(): Promise<void> {
		loading = true;
		errorMessage = '';
		runStatus = '';
		diagnosticsPath = '';
		resultMarkdown = '';
		runWarnings = [];

		try {
			const response = await fetch('/api/deep-dive', {
				method: 'POST',
				headers: { 'content-type': 'application/json' },
				body: JSON.stringify({
					title: title.trim() || null,
					suggest,
					process_mode: processMode,
					dry_run: dryRun
				})
			});

			const payload = await response.json();
			if (!response.ok) {
				throw new Error(payload?.detail ?? 'Request failed');
			}

			runStatus = payload.status;
			diagnosticsPath = payload.diagnostics_path;
			resultMarkdown = payload.markdown;
			runWarnings = Array.isArray(payload.warnings) ? payload.warnings : [];
		} catch (error) {
			errorMessage = String(error);
		} finally {
			loading = false;
		}
	}
</script>

<main class="relative overflow-hidden px-5 py-10 md:px-10 md:py-14">
	<div class="mx-auto grid w-full max-w-6xl gap-6 lg:grid-cols-[1.5fr_1fr]">
		<section class="space-y-6 rounded-3xl border border-white/30 bg-white/70 p-6 shadow-xl backdrop-blur md:p-10">
			<Badge class="preset-filled-secondary-500 mb-2 border-0">Custerion Collection UI</Badge>
			<h1 class="text-4xl font-bold leading-tight text-balance md:text-6xl">
				Curate stories and diagnostics in one expressive workspace.
			</h1>
			<p class="max-w-2xl text-base text-muted-foreground md:text-lg">
				This frontend is bootstrapped with SvelteKit + Tailwind and composed with shadcn-svelte,
				Bits UI primitives, and Skeleton styling for fast iteration with polish.
			</p>
			<div class="inline-flex w-fit items-center gap-2 rounded-full border border-black/10 bg-white/80 px-3 py-1 text-sm">
				<span class="h-2 w-2 rounded-full {backendStatus === 'online' ? 'bg-green-500' : 'bg-red-500'}"></span>
				Backend: {backendStatus}
			</div>
			<div class="flex flex-wrap gap-3">
				<Button
					class="preset-filled-primary-500 border-0"
					onclick={() => document.getElementById('run-deep-dive')?.scrollIntoView({ behavior: 'smooth' })}
				>
					Start a Deep Dive
				</Button>
				<Button
					variant="outline"
					onclick={async () => {
						await loadArtifacts();
						document.getElementById('saved-artifacts')?.scrollIntoView({ behavior: 'smooth' });
					}}
				>
					Browse Saved Artifacts
				</Button>
			</div>

			<Card.Root class="mt-6 border-black/5 bg-white/85">
				<Card.Header>
					<Card.Title class="text-2xl">Pipeline Status</Card.Title>
					<Card.Description>Current readiness across core collection systems.</Card.Description>
				</Card.Header>
				<Card.Content class="space-y-5">
					{#each focusAreas as area}
						<div class="space-y-2">
							<div class="flex items-center justify-between text-sm">
								<span>{area.label}</span>
								<span class="font-semibold">{area.score}</span>
							</div>
							<Progress value={Number.parseInt(area.score)} max={100} class="space-y-1">
								<Progress.Track class="h-2 rounded-full bg-black/10">
									<Progress.Range class="preset-filled-primary-500 h-full rounded-full" />
								</Progress.Track>
							</Progress>
						</div>
					{/each}
				</Card.Content>
			</Card.Root>
		</section>

		<section class="space-y-5 rounded-3xl border border-black/5 bg-white/75 p-6 shadow-lg backdrop-blur md:p-8">
			<h2 class="text-3xl font-bold">Quick Peek</h2>
			<p class="text-sm text-muted-foreground">
				A lightweight example using Bits UI dialog primitives while the visual styling stays in your
				design system.
			</p>

			<Dialog.Root>
				<Dialog.Trigger class="preset-filled-tertiary-500 w-full rounded-xl px-4 py-3 text-left font-semibold">
					Open Session Snapshot
				</Dialog.Trigger>
				<Dialog.Portal>
					<Dialog.Overlay class="fixed inset-0 z-40 bg-black/45 backdrop-blur-sm" />
					<Dialog.Content class="fixed left-1/2 top-1/2 z-50 w-[92vw] max-w-lg -translate-x-1/2 -translate-y-1/2 rounded-2xl border border-white/20 bg-white p-6 shadow-2xl">
						<Dialog.Title class="text-2xl font-bold">Collection Snapshot</Dialog.Title>
						<Dialog.Description class="mt-2 text-sm text-muted-foreground">
							Recent live test run completed within quota and generated artifacts successfully.
						</Dialog.Description>
						<ul class="mt-5 space-y-2 text-sm">
							<li class="preset-filled-success-500 rounded-lg px-3 py-2">Live integration checks: passing</li>
							<li class="preset-filled-primary-500 rounded-lg px-3 py-2">Diagnostics written: 2 records</li>
							<li class="preset-filled-warning-500 rounded-lg px-3 py-2">Follow-up: add artifact filtering UI</li>
						</ul>
						<Dialog.Close class="mt-6 inline-flex rounded-lg border border-black/10 px-4 py-2 text-sm font-medium hover:bg-black/5">
							Close
						</Dialog.Close>
					</Dialog.Content>
				</Dialog.Portal>
			</Dialog.Root>

			<div class="rounded-2xl border border-dashed border-black/10 p-4 text-sm text-muted-foreground">
				Integration status: this UI is live-wired to FastAPI via SvelteKit server routes.
			</div>
		</section>

		<section id="run-deep-dive" class="space-y-5 rounded-3xl border border-black/5 bg-white/80 p-6 shadow-lg backdrop-blur md:p-8 lg:col-span-2">
			<h2 class="text-3xl font-bold">Run Deep Dive</h2>
			<p class="text-sm text-muted-foreground">This form is fully wired to your backend via SvelteKit server routes.</p>

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
					Dry run
				</label>
				<label class="inline-flex items-center gap-2">
					<input type="checkbox" bind:checked={suggest} />
					Suggest mode
				</label>
			</div>

			<Button class="preset-filled-primary-500 border-0" onclick={runDeepDive} disabled={loading}>
				{loading ? 'Generating...' : 'Generate'}
			</Button>

			{#if errorMessage}
				<div class="preset-filled-error-500 rounded-xl px-4 py-3 text-sm">{errorMessage}</div>
			{/if}

			{#if runStatus}
				<div class="grid gap-4 md:grid-cols-2">
					<div class="rounded-xl border border-black/10 bg-white p-4 text-sm">
						<div><span class="font-semibold">Status:</span> {runStatus}</div>
						<div class="mt-1"><span class="font-semibold">Diagnostics:</span> {diagnosticsPath}</div>
					</div>
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
							<li class="rounded-lg border border-black/10 px-3 py-2">
								<div class="font-medium">{artifact.title}</div>
								<div class="mt-1 text-xs text-muted-foreground">Updated: {artifact.updated_at}</div>
								{#if artifact.markdown_path}
									<div class="mt-1 text-xs">Markdown: <code>{artifact.markdown_path}</code></div>
								{/if}
								{#if artifact.artifact_json_path}
									<div class="text-xs">JSON: <code>{artifact.artifact_json_path}</code></div>
								{/if}
							</li>
						{/each}
					</ul>
				{/if}
			</div>
		</section>
	</div>
</main>
