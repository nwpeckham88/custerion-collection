<script lang="ts">
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
			<div class="flex flex-wrap gap-3">
				<Button class="preset-filled-primary-500 border-0">Start a Deep Dive</Button>
				<Button variant="outline">Browse Saved Artifacts</Button>
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
							<Progress.Root value={Number.parseInt(area.score)} max={100} class="space-y-1">
								<Progress.Track class="h-2 rounded-full bg-black/10">
									<Progress.Range class="preset-filled-primary-500 h-full rounded-full" />
								</Progress.Track>
							</Progress.Root>
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
				Next: connect this shell to your Python backend endpoints and stream generated artifacts directly.
			</div>
		</section>
	</div>
</main>
