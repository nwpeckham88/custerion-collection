<script lang="ts">
	import { onMount } from 'svelte';
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

	const walkthrough = [
		{
			id: 'step-1',
			title: '1. Configure',
			description: 'Set title, mode, and whether this run should be a dry-run.',
			actionLabel: 'Jump to Form',
			targetId: 'run-deep-dive'
		},
		{
			id: 'step-2',
			title: '2. Generate',
			description: 'Run the deep dive and inspect run status, warnings, and diagnostics path.',
			actionLabel: 'Run Now',
			targetId: 'run-deep-dive'
		},
		{
			id: 'step-3',
			title: '3. Review',
			description: 'Browse saved artifacts and open generated files from your data directory.',
			actionLabel: 'See Artifacts',
			targetId: 'saved-artifacts'
		}
	] as const;

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

	function jumpTo(id: string): void {
		document.getElementById(id)?.scrollIntoView({ behavior: 'smooth', block: 'start' });
	}

	function walkthroughStatus(stepId: string): 'ready' | 'in progress' | 'done' {
		if (stepId === 'step-1') {
			return title.trim() || suggest ? 'done' : 'ready';
		}
		if (stepId === 'step-2') {
			if (loading) {
				return 'in progress';
			}
			return runStatus ? 'done' : 'ready';
		}
		return artifacts.length > 0 ? 'done' : 'ready';
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
		<section class="rounded-3xl border border-black/10 bg-white/80 p-6 shadow-xl backdrop-blur md:p-10">
			<div class="flex flex-wrap items-start justify-between gap-4">
				<div class="space-y-4">
					<Badge class="preset-filled-secondary-500 border-0">Custerion Collection</Badge>
					<h1 class="max-w-3xl text-4xl font-bold leading-tight text-balance md:text-6xl">
						Generate guided film deep-dives from one production-ready workspace.
					</h1>
					<p class="max-w-2xl text-base text-muted-foreground md:text-lg">
						Use the step cards below to configure, run, and review your deep-dive artifacts.
					</p>
				</div>
				<div class="inline-flex h-fit items-center gap-2 rounded-full border border-black/10 bg-white px-3 py-1 text-sm">
					<span class="h-2 w-2 rounded-full {backendStatus === 'online' ? 'bg-green-500' : 'bg-red-500'}"></span>
					Backend: {backendStatus}
				</div>
			</div>

			<div class="mt-6 grid gap-4 md:grid-cols-3">
				{#each walkthrough as step}
					<Card.Root class="border-black/10 bg-white">
						<Card.Header class="space-y-2">
							<div class="flex items-center justify-between gap-2">
								<Card.Title class="text-xl">{step.title}</Card.Title>
								<Badge class="border-0 {walkthroughStatus(step.id) === 'done' ? 'preset-filled-success-500' : walkthroughStatus(step.id) === 'in progress' ? 'preset-filled-warning-500' : 'preset-filled-surface-500'}">
									{walkthroughStatus(step.id)}
								</Badge>
							</div>
							<Card.Description>{step.description}</Card.Description>
						</Card.Header>
						<Card.Content>
							<Button variant="outline" class="w-full" onclick={() => jumpTo(step.targetId)}>{step.actionLabel}</Button>
						</Card.Content>
					</Card.Root>
				{/each}
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
					{loading ? 'Generating...' : 'Generate'}
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
					<div><span class="font-semibold">Status:</span> {runStatus}</div>
					<div class="mt-1"><span class="font-semibold">Diagnostics:</span> {diagnosticsPath}</div>
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
							</li>
						{/each}
					</ul>
				{/if}
			</div>
		</section>
	</div>
</main>
