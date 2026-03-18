<script lang="ts">
	import { onMount, tick } from 'svelte';
	import { Badge } from '$lib/components/ui/badge';
	import { Button } from '$lib/components/ui/button';

	type ArtifactSummary = {
		title: string;
		slug: string;
		markdown_path: string | null;
		artifact_json_path: string | null;
		html_path: string | null;
		tts_audio_path: string | null;
		updated_at: string;
	};

	type ThemeMode = 'light' | 'dark';

	let title = $state('Blade Runner (1982)');
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
	let themeMode = $state<ThemeMode>('light');

	function applyTheme(mode: ThemeMode): void {
		themeMode = mode;
		document.documentElement.classList.toggle('dark', mode === 'dark');
		localStorage.setItem('custerion-theme', mode);
	}

	function syncThemeFromSystem(): void {
		const stored = localStorage.getItem('custerion-theme');
		if (stored === 'light' || stored === 'dark') {
			applyTheme(stored);
			return;
		}

		const prefersDark = window.matchMedia('(prefers-color-scheme: dark)').matches;
		applyTheme(prefersDark ? 'dark' : 'light');
	}

	function toggleTheme(): void {
		applyTheme(themeMode === 'dark' ? 'light' : 'dark');
	}

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
		syncThemeFromSystem();

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

<main class="page-shell">
	<div class="ambient-glow" aria-hidden="true"></div>
	<div class="main-grid">
		<header class="topbar reveal-1">
			<div class="brand-row">
				<Badge class="brand-badge" variant="outline">Custerion Collection</Badge>
				<span class="brand-subtitle">Cinematic analysis engine</span>
			</div>
			<div class="topbar-actions">
				<div class="service-pill {backendStatus === 'online' ? 'service-pill-up' : 'service-pill-down'}">
					<span class="status-dot"></span>
					Backend {backendStatus}
				</div>
				<Button variant="outline" size="sm" class="theme-toggle" onclick={toggleTheme}>
					{themeMode === 'dark' ? 'Light Mode' : 'Dark Mode'}
				</Button>
			</div>
		</header>

		<section class="hero reveal-2">
			<div class="hero-left">
				<h1>Generate rich film deep-dives from a single title.</h1>
				<p>
					Custerion runs a multi-agent analysis, tracks progress in real time, and stores polished markdown, JSON, and HTML artifacts for later review.
				</p>
			</div>
			<div class="hero-right">
				<div class="hero-stat">
					<span>Workflow</span>
					<strong>Start run -> Monitor -> Open report</strong>
				</div>
				<div class="hero-stat">
					<span>Artifacts loaded</span>
					<strong>{artifacts.length}</strong>
				</div>
				<div class="hero-stat">
					<span>Process mode</span>
					<strong>{processMode}</strong>
				</div>
			</div>
		</section>

		<div class="content-grid">
			<section class="panel control-panel reveal-3">
				<div class="panel-header">
					<h2>Run a Deep Dive</h2>
					<p>Set your title and run options, then generate.</p>
				</div>

				<div class="form-grid">
					<label class="field">
						<span>Film title</span>
						<input bind:value={title} placeholder="e.g., Blade Runner (1982)" />
					</label>

					<label class="field">
						<span>Process mode</span>
						<select bind:value={processMode}>
							<option value="hierarchical">hierarchical</option>
							<option value="sequential">sequential</option>
						</select>
					</label>
				</div>

				<div class="switches">
					<label><input type="checkbox" bind:checked={dryRun} /> Dry run for smoke testing</label>
					<label><input type="checkbox" bind:checked={suggest} /> Suggest mode (title optional)</label>
				</div>

				<div class="actions">
					<Button class="run-button" onclick={runDeepDive} disabled={loading}>
						{loading ? 'Running analysis...' : 'Generate Deep Dive'}
					</Button>
					<Button variant="outline" onclick={loadArtifacts} disabled={artifactsLoading}>
						{artifactsLoading ? 'Refreshing...' : 'Refresh Artifacts'}
					</Button>
				</div>

				{#if errorMessage}
					<div class="message error">{errorMessage}</div>
				{/if}

				{#if runStatus}
					<div class="message status">
						<div><strong>Status:</strong> {runStatus}</div>
						{#if runId}
							<div><strong>Run ID:</strong> <code>{runId}</code></div>
						{/if}
						{#if runStage}
							<div><strong>Stage:</strong> {runStage}</div>
						{/if}
						<div><strong>Progress:</strong> {runProgress}%</div>
						<div><strong>Diagnostics:</strong> {diagnosticsPath || 'pending...'}</div>
						<div class="progress-track" role="progressbar" aria-label="Run progress" aria-valuemin="0" aria-valuemax="100" aria-valuenow={runProgress}>
							<div class="progress-fill" style={`width: ${runProgress}%`}></div>
						</div>
					</div>
				{/if}

				{#if runEvents.length > 0}
					<div class="events-shell">
						<div class="events-title">Agent conversation</div>
						<div class="events-log" bind:this={runEventsPanel}>
							{#each runEvents as event}
								<div>{event}</div>
							{/each}
						</div>
					</div>
				{/if}

				{#if runWarnings.length > 0}
					<div class="message warning">
						<strong>Warnings</strong>
						<ul>
							{#each runWarnings as warning}
								<li>{warning}</li>
							{/each}
						</ul>
					</div>
				{/if}
			</section>

			<section class="panel artifacts-panel reveal-4">
				<div class="panel-header">
					<h2>Recent Artifacts</h2>
					<p>Open HTML reports or guided commentary from saved runs.</p>
				</div>

				{#if artifactsError}
					<div class="message error">{artifactsError}</div>
				{:else if artifacts.length === 0}
					<div class="empty-state">No artifacts yet. Run your first deep dive to populate this list.</div>
				{:else}
					<ul class="artifact-list">
						{#each artifacts as artifact}
							<li>
								<div class="artifact-head">
									<strong>{artifact.title}</strong>
									<span>{artifact.updated_at}</span>
								</div>
								<div class="artifact-links">
									{#if artifact.html_path}
										<a href={`/artifacts/${artifact.slug}/report`} target="_blank" rel="noopener noreferrer">Open report page</a>
									{/if}
									<a href={`/artifacts/${artifact.slug}/commentary`}>Open guided commentary</a>
									{#if artifact.tts_audio_path}
										<a href={`/artifacts/${artifact.slug}/tts`}>Open TTS commentary</a>
									{/if}
								</div>
								<div class="artifact-actions">
									<Button
										variant="outline"
										size="sm"
										onclick={() => regenerateArtifactHtml(artifact.slug)}
										disabled={regeneratingSlug === artifact.slug}
									>
										{regeneratingSlug === artifact.slug ? 'Regenerating...' : 'Regenerate HTML'}
									</Button>
								</div>
								{#if artifactRegenerateErrors[artifact.slug]}
									<div class="artifact-error">{artifactRegenerateErrors[artifact.slug]}</div>
								{/if}
							</li>
						{/each}
					</ul>
				{/if}
			</section>
		</div>

		{#if resultMarkdown}
			<section class="panel markdown-panel reveal-4">
				<div class="panel-header">
					<h2>Latest Markdown Output</h2>
					<p>Raw output from the most recent completed run.</p>
				</div>
				<pre>{resultMarkdown}</pre>
			</section>
		{/if}
	</div>
</main>

<style>
	.page-shell {
		--accent-brand: oklch(0.62 0.16 252);
		--accent-warm: oklch(0.72 0.14 68);
		--panel-bg: color-mix(in oklch, white 84%, var(--background));
		--panel-border: color-mix(in oklch, var(--foreground) 16%, transparent);
		--field-bg: color-mix(in oklch, white 70%, var(--background));
		--text-strong: color-mix(in oklch, var(--foreground) 96%, black);
		--text-muted: color-mix(in oklch, var(--foreground) 62%, white);
		position: relative;
		min-height: 100vh;
		padding: 1.25rem;
	}

	:global(.dark) .page-shell {
		--accent-brand: oklch(0.8 0.1 245);
		--accent-warm: oklch(0.83 0.11 86);
		--panel-bg: color-mix(in oklch, var(--background) 88%, white 12%);
		--panel-border: color-mix(in oklch, white 28%, transparent);
		--field-bg: color-mix(in oklch, var(--background) 74%, white 26%);
		--text-strong: oklch(0.97 0 0);
		--text-muted: oklch(0.84 0.01 260);
	}

	.ambient-glow {
		position: fixed;
		inset: 0;
		pointer-events: none;
		background:
			radial-gradient(circle at 9% 14%, color-mix(in oklch, var(--accent-brand) 24%, transparent), transparent 38%),
			radial-gradient(circle at 90% 8%, color-mix(in oklch, var(--accent-warm) 22%, transparent), transparent 36%);
	}

	.main-grid {
		position: relative;
		z-index: 1;
		max-width: 1220px;
		margin: 0 auto;
		display: grid;
		gap: 1rem;
	}

	.topbar,
	.hero,
	.panel {
		border: 1px solid var(--panel-border);
		background: var(--panel-bg);
		backdrop-filter: blur(20px);
		border-radius: 1.25rem;
		box-shadow: var(--panel-shadow);
	}

	.topbar {
		display: flex;
		justify-content: space-between;
		align-items: center;
		gap: 1rem;
		padding: 0.9rem 1rem;
	}

	.brand-row {
		display: flex;
		align-items: center;
		gap: 0.65rem;
		flex-wrap: wrap;
	}

	:global(.brand-badge) {
		border-color: var(--accent-brand);
		color: var(--text-strong);
		background: color-mix(in oklch, var(--accent-brand) 16%, transparent);
	}

	.brand-subtitle {
		font-size: 0.86rem;
		color: var(--text-muted);
	}

	.topbar-actions {
		display: flex;
		align-items: center;
		gap: 0.55rem;
		flex-wrap: wrap;
		justify-content: flex-end;
	}

	.service-pill {
		display: inline-flex;
		align-items: center;
		gap: 0.4rem;
		padding: 0.4rem 0.65rem;
		font-size: 0.78rem;
		border-radius: 999px;
		border: 1px solid transparent;
	}

	.service-pill-up {
		background: color-mix(in oklch, #17a34a 16%, transparent);
		border-color: color-mix(in oklch, #17a34a 38%, transparent);
	}

	.service-pill-down {
		background: color-mix(in oklch, #db3f4f 16%, transparent);
		border-color: color-mix(in oklch, #db3f4f 38%, transparent);
	}

	.status-dot {
		width: 0.52rem;
		height: 0.52rem;
		border-radius: 999px;
		background: currentColor;
	}

	:global(.theme-toggle) {
		border-radius: 999px;
	}

	.hero {
		display: grid;
		grid-template-columns: 1.35fr 1fr;
		gap: 1rem;
		padding: 1.25rem;
	}

	.hero h1 {
		font-size: clamp(1.8rem, 3.2vw, 3.05rem);
		line-height: 1.06;
		font-weight: 600;
		letter-spacing: -0.02em;
		max-width: 18ch;
	}

	.hero p {
		margin-top: 0.85rem;
		font-size: 1rem;
		line-height: 1.52;
		max-width: 52ch;
		color: var(--text-muted);
	}

	.hero-right {
		display: grid;
		gap: 0.5rem;
	}

	.hero-stat {
		padding: 0.8rem;
		border-radius: 0.95rem;
		background: color-mix(in oklch, var(--panel-bg) 72%, transparent);
		border: 1px solid var(--panel-border);
		display: grid;
		gap: 0.25rem;
	}

	.hero-stat span {
		font-size: 0.72rem;
		text-transform: uppercase;
		letter-spacing: 0.07em;
		color: var(--text-muted);
	}

	.hero-stat strong {
		font-size: 0.95rem;
	}

	.content-grid {
		display: grid;
		grid-template-columns: 1.2fr 1fr;
		gap: 1rem;
	}

	.panel {
		padding: 1rem;
	}

	.panel-header h2 {
		font-size: 1.2rem;
		font-weight: 600;
	}

	.panel-header p {
		margin-top: 0.2rem;
		font-size: 0.9rem;
		color: var(--text-muted);
	}

	.form-grid {
		margin-top: 0.9rem;
		display: grid;
		grid-template-columns: 1fr 1fr;
		gap: 0.65rem;
	}

	.field {
		display: grid;
		gap: 0.35rem;
	}

	.field span {
		font-size: 0.79rem;
		font-weight: 500;
		color: var(--text-muted);
	}

	.field input,
	.field select {
		width: 100%;
		border-radius: 0.8rem;
		padding: 0.6rem 0.75rem;
		border: 1px solid var(--panel-border);
		background: var(--field-bg);
		color: var(--text-strong);
		outline: none;
	}

	.field input:focus,
	.field select:focus {
		border-color: color-mix(in oklch, var(--accent-brand) 58%, var(--panel-border));
		box-shadow: 0 0 0 3px color-mix(in oklch, var(--accent-brand) 18%, transparent);
	}

	.switches {
		margin-top: 0.9rem;
		display: flex;
		flex-direction: column;
		gap: 0.45rem;
		font-size: 0.86rem;
		color: var(--text-muted);
	}

	.switches label {
		display: inline-flex;
		align-items: center;
		gap: 0.5rem;
	}

	.actions {
		margin-top: 0.95rem;
		display: flex;
		flex-wrap: wrap;
		gap: 0.55rem;
	}

	:global(.run-button) {
		background: linear-gradient(135deg, var(--accent-brand), color-mix(in oklch, var(--accent-brand) 45%, white));
		color: white;
		border: 0;
	}

	.message {
		margin-top: 0.8rem;
		padding: 0.68rem 0.78rem;
		border-radius: 0.8rem;
		font-size: 0.84rem;
		display: grid;
		gap: 0.3rem;
	}

	.message.error {
		border: 1px solid color-mix(in oklch, #e11d48 38%, transparent);
		background: color-mix(in oklch, #e11d48 14%, transparent);
	}

	.message.status {
		border: 1px solid var(--panel-border);
		background: color-mix(in oklch, var(--field-bg) 72%, transparent);
	}

	.progress-track {
		height: 0.42rem;
		border-radius: 999px;
		background: color-mix(in oklch, var(--text-muted) 28%, transparent);
		overflow: hidden;
	}

	.progress-fill {
		height: 100%;
		background: linear-gradient(90deg, var(--accent-brand), var(--accent-warm));
		transition: width 280ms ease;
	}

	.events-shell {
		margin-top: 0.85rem;
	}

	.events-title {
		font-size: 0.83rem;
		text-transform: uppercase;
		letter-spacing: 0.06em;
		color: var(--text-muted);
	}

	.events-log {
		margin-top: 0.45rem;
		max-height: 15rem;
		overflow: auto;
		padding: 0.75rem;
		border-radius: 0.82rem;
		border: 1px solid var(--panel-border);
		background: color-mix(in oklch, var(--field-bg) 68%, transparent);
		font-size: 0.77rem;
		line-height: 1.55;
		font-family: 'IBM Plex Mono', monospace;
	}

	.message.warning {
		border: 1px solid color-mix(in oklch, #c27b14 46%, transparent);
		background: color-mix(in oklch, #f4b03d 18%, transparent);
	}

	.message.warning ul {
		margin: 0.2rem 0 0;
		padding-left: 1.1rem;
	}

	.empty-state {
		margin-top: 0.85rem;
		padding: 0.75rem;
		border-radius: 0.8rem;
		border: 1px dashed var(--panel-border);
		font-size: 0.86rem;
		color: var(--text-muted);
	}

	.artifact-list {
		margin-top: 0.85rem;
		display: grid;
		gap: 0.62rem;
	}

	.artifact-list li {
		padding: 0.7rem;
		border-radius: 0.8rem;
		border: 1px solid var(--panel-border);
		background: color-mix(in oklch, var(--field-bg) 66%, transparent);
	}

	.artifact-head {
		display: flex;
		justify-content: space-between;
		align-items: flex-start;
		gap: 0.6rem;
	}

	.artifact-head strong {
		font-size: 0.9rem;
	}

	.artifact-head span {
		font-size: 0.73rem;
		color: var(--text-muted);
	}

	.artifact-links {
		margin-top: 0.45rem;
		display: flex;
		gap: 0.78rem;
		flex-wrap: wrap;
		font-size: 0.79rem;
	}

	.artifact-links a {
		color: var(--accent-brand);
		text-decoration: underline;
		text-decoration-style: dotted;
		text-underline-offset: 0.14rem;
	}

	.artifact-actions {
		margin-top: 0.55rem;
	}

	.artifact-error {
		margin-top: 0.45rem;
		font-size: 0.73rem;
		color: #d22452;
		word-break: break-word;
	}

	.markdown-panel pre {
		margin-top: 0.75rem;
		max-height: 24rem;
		overflow: auto;
		padding: 0.85rem;
		border-radius: 0.85rem;
		border: 1px solid var(--panel-border);
		background: color-mix(in oklch, var(--field-bg) 74%, transparent);
		font-size: 0.8rem;
		line-height: 1.48;
		white-space: pre-wrap;
	}

	.reveal-1,
	.reveal-2,
	.reveal-3,
	.reveal-4 {
		opacity: 0;
		transform: translateY(10px);
		animation: rise-in 420ms cubic-bezier(0.2, 0.72, 0.2, 1) forwards;
	}

	.reveal-2 {
		animation-delay: 80ms;
	}

	.reveal-3 {
		animation-delay: 150ms;
	}

	.reveal-4 {
		animation-delay: 210ms;
	}

	@keyframes rise-in {
		to {
			opacity: 1;
			transform: translateY(0);
		}
	}

	@media (max-width: 1024px) {
		.hero,
		.content-grid {
			grid-template-columns: 1fr;
		}
	}

	@media (max-width: 640px) {
		.page-shell {
			padding: 0.85rem;
		}

		.topbar {
			align-items: flex-start;
			flex-direction: column;
		}

		.form-grid {
			grid-template-columns: 1fr;
		}
	}
</style>
