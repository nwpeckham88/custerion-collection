# Custerion Collection

CrewAI-based scaffold for generating personalized film deep-dives.

## What This Scaffold Includes
- CrewAI orchestration with hierarchical process.
- Specialist agents and section tasks.
- Structured artifact models for deep-dive output and follow-up media.
- Local storage hooks for output persistence.
- CLI entrypoint to run one deep-dive.

## Quick Start
1. Create and activate a Python 3.11+ environment.
2. Install dependencies:

```bash
pip install -e .
```

3. Configure environment variables:

```bash
cp .env.example .env
```

4. Run:

```bash
custerion --title "The Red Shoes"
```

## OpenRouter Setup
To use OpenRouter as the OpenAI-compatible backend:

```bash
OPENAI_API_KEY=<your_openrouter_key>
OPENAI_BASE_URL=https://openrouter.ai/api/v1
MODEL_NAME=openrouter/openai/gpt-4.1-mini
```

`OPENAI_BASE_URL` must include protocol (`https://`).

Optional multi-model routing by role:

```bash
MODEL_NAME_TECHNICAL_DIRECTOR=openrouter/deepseek/deepseek-chat-v3-0324
MODEL_NAME_SCRIPT_EDITOR=openrouter/openai/gpt-4.1
```

Role override key format is `MODEL_NAME_<ROLE_NAME>`, where role names are uppercase with spaces replaced by underscores.

Use `--suggest` instead of `--title` to run suggestion mode.

Override process mode per run:

```bash
custerion --title "The Red Shoes" --process-mode sequential
```

Run a deterministic smoke pass without CrewAI/network calls:

```bash
custerion --title "The Red Shoes" --dry-run
```

## Export Artifact Schema
```bash
custerion --export-schema
```

Optional custom path:

```bash
custerion --export-schema --schema-output ./data/schemas/deep_dive.schema.json
```

## Run Tests
```bash
PYTHONPATH=src python -m unittest discover -s tests -v
```

## Live LLM Tests (Rate-Limited)
Live tests are opt-in and budget-controlled so local runs do not exhaust API quota.

Environment controls:
- `RUN_LLM_LIVE_TESTS=1`: enable live LLM tests (default is disabled/skip).
- `LLM_LIVE_TEST_MAX_CALLS_PER_DAY=3`: max live test executions per UTC day.
- `LLM_LIVE_TEST_COOLDOWN_SECONDS=20`: enforced wait between live test executions.
- `LLM_LIVE_TEST_QUOTA_PATH=...`: optional custom path for quota state file.
- `LLM_LIVE_TEST_MODEL=...`: optional model override for the live smoke test.

Example:

```bash
RUN_LLM_LIVE_TESTS=1 \
LLM_LIVE_TEST_MAX_CALLS_PER_DAY=2 \
LLM_LIVE_TEST_COOLDOWN_SECONDS=30 \
PYTHONPATH=src python -m unittest tests.test_live_llm_integration -v
```

Note: if you use OpenRouter without installing `litellm`, set `LLM_LIVE_TEST_MODEL`
with an OpenAI provider prefix (for example `openai/nvidia/nemotron-...`) so
CrewAI can initialize via its native OpenAI provider path.

## CI/CD
- CI runs on pushes/PRs to `main`/`master` and executes tests, schema export, and dry-run smoke checks.
- CD runs on pushed tags matching `v*`, builds wheel/sdist, and publishes a GitHub Release with build artifacts.

Release example:

```bash
git tag v0.1.0
git push origin v0.1.0
```

## Notes
- Retrieval adapters are wired for Jellyfin, Wikipedia, TMDb, and optional YouTube.
- Set `JELLYFIN_URL`, `JELLYFIN_API_KEY`, and `JELLYFIN_USER_ID` for personalization context.
- Set `TMDB_API_KEY` for technical/industry context and related-film follow-ups.
- Set `YOUTUBE_API_KEY` to include interview/essay videos in follow-up media.
- Generated artifacts are written under `data/artifacts/` as both markdown (`.md`) and structured JSON (`.json`).
- JSON schema is written under `data/schemas/` by default.
- Run diagnostics are written under `data/diagnostics/` for each run.
- Follow-Up Media is intentionally scoped to avoid feature creep.
- External HTTP adapters support retry tuning with `HTTP_RETRY_COUNT` and `HTTP_RETRY_BACKOFF_SECONDS`.
- Crew process mode can be set with `PROCESS_MODE=hierarchical|sequential`.
