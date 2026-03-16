# Criterion Deep-Dive System Design (CrewAI)

## 1. Purpose
Build a CrewAI-based system that produces a high-quality film deep-dive ("guided tour") tailored to the user, using personal media context plus curated external sources.

The output must be editorially coherent, evidence-based, personalized, and explicit about uncertainty.

## 2. Product Scope

### In Scope
- Generate one complete deep-dive package for a selected film.
- Personalize framing and recommendations using Jellyfin history plus explicit endorsements/dislikes.
- Persist deep-dives, source ledgers, and preference signals for future sessions.
- Support both user-directed prompts ("deep-dive this title") and system-suggested titles.
- Execute orchestration through CrewAI `Crew` runs using explicit `Agent` and `Task` definitions.
- Include a bounded "Follow-Up Media" appendix with relevant links for further exploration.

### Out of Scope
- Building the final interactive frontend experience.
- Real-time chat during generation.
- Autonomous social posting or outbound publishing.
- General-purpose open-web search outside approved domains.
- Full recommendation-system redesign beyond this deep-dive workflow.

## 3. Design Principles
- Evidence over style: claims must be linked to sources.
- Cohesion over parallel noise: many specialists may contribute, but one editorial voice owns synthesis.
- Personalization without lock-in: taste signals shape priority, not truth.
- Deterministic where practical: same inputs should produce similar structure and ranking.
- Graceful degradation: missing sources reduce depth, not availability.
- Scoped ambition: add value without uncontrolled feature growth.

## 4. Primary Actors
- User: requests a deep-dive or accepts a suggestion.
- CrewAI Orchestrator: `Crew` runtime that coordinates task order, tool access, and run state.
- Specialist Agents: CrewAI `Agent` instances that retrieve and structure evidence from bounded domains.
- Editor Agent: CrewAI `Agent` that composes final narrative and applies quality gates.
- Memory Store: persists preferences, run history, artifacts, and feedback.

## 5. Critical System Decisions

### Decision: Hierarchical Multi-Agent Orchestration
Use CrewAI hierarchical process (`Process.hierarchical`) with a manager-led structure rather than a flat peer network.

Rationale:
- Reduces duplicated research and conflicting conclusions.
- Enforces section ownership and narrative flow.
- Simplifies quality control and source validation.

Trade-off:
- Manager quality is a single point of failure.

Mitigation:
- Require explicit task plans, completion checks, and section-level acceptance criteria.

### Decision: CrewAI as Orchestration Framework
Represent workflow components with CrewAI first-class objects (`Agent`, `Task`, `Crew`) instead of custom orchestration logic.

Rationale:
- Reduces custom control-plane code for sequencing and handoff.
- Makes role definitions and task contracts explicit and inspectable.
- Improves maintainability as specialist roles evolve.

Trade-off:
- Runtime behavior and performance depend on CrewAI abstractions and version behavior.

Mitigation:
- Keep tasks deterministic, pin dependency versions, and keep adapter layer thin.

### Decision: Domain-Locked Retrieval
Agents may query only approved providers for their domain (history, technical, finance, trivia, trend, follow-up media).

Rationale:
- Improves factual reliability and source consistency.
- Reduces hallucinations from unconstrained search.

Trade-off:
- Sparse films may have thin coverage.

Mitigation:
- Fall back to "insufficient evidence" notes and surface confidence clearly.

### Decision: Local-First Memory
User preference signals and generated artifacts are stored locally by default.

Rationale:
- Matches privacy expectations for personal watch behavior.
- Preserves continuity without external dependency.

Trade-off:
- Backup/sync burden stays with the user.

Mitigation:
- Keep artifacts exportable and schema-stable for future sync options.

## 6. End-to-End Flow
1. Intake: receive a specific title or suggestion request.
2. Candidate resolution: map input to canonical IDs and local-library matches.
3. Eligibility check: verify minimum source coverage and disambiguate title collisions.
4. Personal context load: gather history, endorsements/dislikes, and prior deep-dives.
5. Crew construction: instantiate CrewAI agents, tasks, tools, and manager policy.
6. Planning: manager agent issues scoped specialist assignments with completion contracts.
7. Evidence collection: specialist tasks return structured findings with claim-to-source links.
8. Claim audit: unsupported claims are rejected, downgraded, or rewritten.
9. Conflict handling: contradictory claims are explicitly represented with rationale.
10. Editorial synthesis: editor task creates one coherent guided-tour narrative.
11. Follow-Up Media curation: follow-up curator task produces a bounded set of links.
12. Persistence: save artifact, source ledger, feedback hooks, and run diagnostics.

## 7. Agent Panel and Responsibilities

### Manager (Creative Director)
- Decomposes work, enforces non-overlap, tracks completeness.
- Applies pre-synthesis quality gates.
- CrewAI note: configured as manager role in hierarchical process.

### Curator (Personal Matchmaker)
- Interprets user taste from watch and endorsement signals.
- Produces "why this film, why now" framing.

### Trend Scout (Industry Context)
- Adds present-day relevance (anniversaries, restorations, festival resurfacing, discourse momentum).

### Cultural Historian
- Anchors the film in historical, critical, and artistic context.

### Technical Director
- Surfaces craft insights (cinematography, editing, sound, VFX, form-language).

### Industrial Analyst
- Covers production economics, release strategy, and market impact.

### Trivia Archivist
- Adds high-signal production stories and cast/crew context.

### Follow-Up Curator
- Collects optional external media links (videos, essays, interviews, related films).
- Applies scope and quality rules to prevent low-value link dumping.

### Editor (Script Editor)
- Produces final single-voice narrative with section transitions.
- Ensures every section passes source and confidence standards.

## 8. CrewAI Implementation Model

### Core Objects
- `Agent`: one per specialist role plus manager and editor.
- `Task`: one task per output section, with explicit expected output contracts.
- `Crew`: single deep-dive run composed of all tasks and agents.

### Process Mode
- Primary mode: `Process.hierarchical` with manager oversight.
- Optional fallback: `Process.sequential` for constrained environments and debugging.

### Task Contracts
- Every task must define objective, required inputs, expected output schema, and acceptance checks.
- Task outputs should be machine-parseable where feasible to simplify synthesis and persistence.

### Tooling Model
- Agents receive only domain-approved tools.
- Tool access is deny-by-default; capabilities are granted per role.

## 9. Output Contract
Each deep-dive must contain:
- Film identity block: canonical title, year, key credits, runtime, language, canonical IDs.
- Personalized intro: why this film is relevant now.
- Core sections: history, craft, industry, cultural impact, notable lore.
- "What to watch next" list with personalized justification.
- Confidence markers for uncertain or disputed claims.
- Source ledger grouped by section.
- Follow-Up Media appendix with short rationale per link.

Tone requirements:
- Professional, engaging, non-academic but expert.
- No fabricated certainty.
- No repetitive voice patterns across sections.

Format requirements:
- Stable section order for predictable rendering.
- Explicit "Known Unknowns" block when evidence is thin or conflicting.

## 10. Follow-Up Media (Scoped Feature)

### Goal
Offer optional "what to explore next" links without overshadowing the deep-dive.

### Content Types
- YouTube interviews, essays, analysis videos.
- High-quality written sources (archives, criticism, production notes).
- Related films with one-line relevance explanation.

### Scope Limits
- Target 5 to 8 links total.
- Maximum 3 links per type.
- Prioritize quality and novelty over quantity.

### Ranking Heuristics
- Relevance to this specific film and generated sections.
- Source credibility and signal quality.
- Personalization fit based on known preferences.
- Diversity across media types (not all videos).

### Quality Rules
- No duplicate links or near-duplicates.
- No clickbait-only sources when alternatives exist.
- Every link includes reason-to-open in one sentence.
- If source confidence is low, omit instead of padding.

### Non-Goals
- Building a full external recommendation feed.
- Continuous monitoring or automatic refreshing of links.

## 11. Data Model Decisions

### Persistent Entities
- FilmProfile: normalized identity and metadata references.
- UserPreferenceSignal: explicit ratings, endorsements/dislikes, inferred affinity vectors.
- WatchEventSummary: aggregate viewing behavior (recency, genre drift, rewatch patterns).
- DeepDiveArtifact: rendered output and structured sections.
- SourceCitation: provider, URL/ID, retrieval timestamp, claim linkage, confidence.
- FollowUpMediaItem: type, URL/ID, title, rationale, source confidence, relevance score.
- RunDiagnostics: agent status, dropped claims, timing, and quality metrics.

### Identity and Matching
- Canonical identity requires external ID mapping to prevent duplicates.
- Local title matching is advisory; canonical ID is authoritative.
- Disambiguation is mandatory before synthesis when multiple canonical matches exist.

### Retention
- Deep-dive artifacts retained indefinitely by default.
- Intermediate notes may be discarded once claim linkage is preserved.
- Follow-up links are retained with timestamp to support stale-link cleanup later.

## 12. Personalization Decisions
- Personalization influences framing and recommendation ranking, never factual interpretation.
- Negative preferences reduce recommendation weight but do not censor context.
- Recency bias is bounded to avoid overfitting to short-term streaks.
- Previously deep-dived films are deprioritized unless user requests revisit.
- Follow-Up Media links should include at least one item outside the strongest affinity cluster to preserve discovery.

## 13. Quality and Trust Decisions

### Fact Integrity
- Every non-trivial factual claim must map to at least one source record.
- Unsupported claims are removed or explicitly marked low confidence.

### Conflict Resolution
- If reputable sources disagree, present disagreement and cite both positions.
- Editor cannot silently choose one claim without rationale.

### Hallucination Guardrails
- No unrestricted open-web retrieval in core workflow.
- No generated quotes unless directly sourced.
- No fabricated production anecdotes.

### Follow-Up Link Trust
- Links must come from approved domains/providers.
- Dead/unreachable links are excluded at generation time when possible.

## 14. Reliability, Cost, and Latency Targets
- Availability target: successful artifact generation for at least 95% of valid title requests.
- Latency target: p50 less than 45 seconds, p95 less than 120 seconds for full deep-dive.
- Cost guardrail: configurable per-run budget with early-stop on diminishing returns.
- Concurrency policy: specialist fan-out allowed only when source budgets remain within limits.

## 15. Failure and Degradation Strategy
- If one specialist fails, continue with reduced depth and mark impacted sections.
- If personalization data is unavailable, generate a generic deep-dive and note degraded mode.
- If film identity remains ambiguous, stop before synthesis and request disambiguation.
- If follow-up media retrieval fails, omit the appendix and record a non-fatal warning.

## 16. Observability and Evaluation

### Run Observability
- Track per-agent completion, source counts, confidence distribution, dropped-claim counts, and token/runtime costs.

### Quality Evaluation
- Editorial coherence score.
- Citation coverage ratio.
- Personalization relevance score.
- Follow-Up Media engagement proxy (click/open events when available).
- User feedback loop (useful/not useful, accuracy flags).

### Regression Evaluation
- Keep a fixed benchmark set of films and compare output quality deltas across versions.
- Fail release if citation coverage or coherence regresses beyond agreed thresholds.

## 17. Security and Privacy Decisions
- Jellyfin-derived behavior is private user data.
- External queries should transmit only data needed for retrieval.
- Stored preferences and history must be editable and deletable by the user.
- Logs must avoid leaking raw private watch-history payloads.

## 18. Extensibility Decisions
- New specialist roles require distinct evidence domains and explicit non-overlap.
- Output format is contract-based so markdown, HTML, and future UI renderers share one artifact.
- Recommendation policy is pluggable to enable future ranking strategies.
- Follow-Up Media supports additional media types only through the same quality gates and cap rules.

## 19. Explicit Non-Decisions (Deferred)
- Final UI framework and visual design.
- Real-time collaborative editing of deep-dives.
- Cloud sync and multi-device profile portability.
- Multilingual output strategy.
- Fully autonomous crawl/refresh of external media links.

## 20. Open Risks and Mitigations
- Risk: sparse source coverage for obscure films.
Mitigation: expose known unknowns and degrade gracefully.
- Risk: over-personalization narrows discovery.
Mitigation: enforce diversity floor in recommendations and follow-up media.
- Risk: manager bottleneck lowers throughput.
Mitigation: add strict task templates and automated completion checks.
- Risk: stale follow-up links.
Mitigation: record retrieval timestamps and add future stale-link sweeps.

## 21. Decision Summary
- Use hierarchical orchestration with a single editorial owner.
- Implement orchestration directly with CrewAI `Agent`/`Task`/`Crew` primitives.
- Enforce domain-locked retrieval and claim-level citation linkage.
- Keep memory local-first for privacy and continuity.
- Treat confidence, conflict disclosure, and known unknowns as first-class output requirements.
- Add a scoped Follow-Up Media appendix (5 to 8 links) with strict quality and scope caps.