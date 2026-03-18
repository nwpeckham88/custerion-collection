# Custerion Collection

CrewAI-based scaffold for generating personalized film deep-dives.

## Integrated Stack
- Backend API: FastAPI (`/health`, `/deep-dive`, `/artifacts`)
- Frontend: SvelteKit + Tailwind + shadcn-svelte + Bits UI + Skeleton
- Frontend-to-backend wiring: SvelteKit server routes at `frontend/src/routes/api/*`

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
custerion --title "Blade Runner (1982)"
```

## Run As API + Frontend (Local)
Backend API:

```bash
uvicorn custerion_collection.api:app --host 0.0.0.0 --port 8000
```

Frontend app:

```bash
cd frontend
BACKEND_API_URL=http://localhost:8000 pnpm dev
```

Open `http://localhost:5173` and use the "Run Deep Dive" form.

## Docker Compose (Internal Testing)
Build and run both services:

```bash
docker compose up --build
```

Endpoints:
- Frontend: `http://localhost:4173`
- Backend API: `http://localhost:8000`

Proxy endpoints exposed by the frontend server:
- `GET /api/health`
- `POST /api/deep-dive`
- `POST /api/deep-dive/start`
- `GET /api/deep-dive/{runId}`
- `GET /api/artifacts?limit=20`

The backend container persists generated files via `./data:/app/data`.

Stop services:

```bash
docker compose down
```

## OpenRouter Setup
To use OpenRouter as the OpenAI-compatible backend:

```bash
OPENAI_API_KEY=<your_openrouter_key>
OPENAI_BASE_URL=https://openrouter.ai/api/v1
MODEL_NAME=openrouter/nvidia/nemotron-3-super-120b-a12b:free
MODEL_FALLBACKS=openrouter/qwen/qwen3-next-80b-a3b-instruct:free,openrouter/openrouter/free
```

`OPENROUTER_API_KEY` is optional in this project when `OPENAI_API_KEY` is set;
runtime config automatically mirrors it for LiteLLM provider auth.

`OPENAI_BASE_URL` must include protocol (`https://`).

This project includes `litellm` by default, so non-native provider model strings
can be routed through LiteLLM without additional installation.

`MODEL_FALLBACKS` is optional. If the primary model returns provider errors
(for example unavailable model ID or transient provider limits), the backend
automatically retries using each fallback in order.

Optional multi-model routing by role:

```bash
MODEL_NAME_TECHNICAL_DIRECTOR=openrouter/deepseek/deepseek-chat-v3-0324
MODEL_NAME_SCRIPT_EDITOR=openrouter/openai/gpt-4.1
MODEL_NAME_TRIVIA_RESEARCHER=openrouter/qwen/qwen3-next-80b-a3b-instruct:free
```

Role override key format is `MODEL_NAME_<ROLE_NAME>`, where role names are uppercase with spaces replaced by underscores.

Optional dedicated model for HTML report generation:

```bash
MODEL_NAME_HTML_REPORTER=openrouter/qwen/qwen3-next-80b-a3b-instruct:free
```

When `MODEL_NAME_HTML_REPORTER` is unset, the project writes a deterministic styled HTML report locally.

## Local TTS for Generated Reports
Generated HTML reports include an in-page TTS control panel (voice select, play, stop).

- TTS is optional and disabled by default.
- The project uses a single TTS engine: `kokoro-onnx` (Kokoro 82M ONNX runtime).
- To enable TTS, install optional dependencies with `pip install -e .[tts]` and set `ENABLE_TTS=1`.
- The ONNX model and voice binary are downloaded once to cache and then reused.

Optional configuration:

```bash
TTS_DEFAULT_VOICE=af_sarah
TTS_ENGLISH_VOICES=af_sarah,af_heart
TTS_CACHE_DIR=./data/tts-cache
KOKORO_MODEL_URL=https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.0/kokoro-v1.0.onnx
KOKORO_VOICES_URL=https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.0/voices-v1.0.bin
ENABLE_TTS=1
```

Notes:
- Current support target is English-only.
- First playback can take longer while the model is downloaded and initialized.
- Subsequent playback reuses the cached model and cached audio when text/voice are unchanged.

## Goal-Driven Commentary Planning From Subtitles
Importing subtitles in the guided commentary page can now generate a planned audio timeline instead of replaying raw subtitle lines.

- The planner goal is app-controlled (not user-authored) so behavior stays consistent across runs.
- The planner ingests both subtitle cues and the generated report markdown to schedule commentary beats.
- The backend aligns report facts to matching on-screen context and delays delivery by a small buffer.
- Planned timelines are cached to `data/artifacts/*.commentary-plan.json` and reused by `/api/artifacts/{slug}/commentary`.

Optional environment controls:

```bash
COMMENTARY_PLANNING_GOAL="Create spoiler-aware, engaging commentary paced across the runtime"
MODEL_NAME_COMMENTARY_PLANNER=openrouter/qwen/qwen3-next-80b-a3b-instruct:free
```

`MODEL_NAME_COMMENTARY_PLANNER` should point to your highest-quality planning model.
When the planner model fails at runtime, the service falls back to deterministic heuristics.

Use `--suggest` instead of `--title` to run suggestion mode.

Suggestion mode selection order:
- Uses TMDb weekly trending films first when `TMDB_API_KEY` is configured.
- Filters out obvious repeats based on recent Jellyfin resume titles when Jellyfin is configured.
- Falls back to Jellyfin recent titles when TMDb is unavailable.
- Uses a deterministic fallback title only when provider data is unavailable.

## Quality Gates
To prevent low-value artifacts, non-dry-run deep-dive outputs must pass minimum quality checks before persistence:

- Output length must meet a minimum markdown size threshold.
- Output must include at least 2 substantive (non-placeholder) core sections.
- Citation coverage ratio must meet a minimum threshold.

If a run fails these gates, it is marked failed, diagnostics are written under `data/diagnostics/`, and the API/CLI returns a clear error instead of saving a weak artifact as success.

Override process mode per run:

```bash
custerion --title "Blade Runner (1982)" --process-mode sequential
```

Run a deterministic smoke pass without CrewAI/network calls:

```bash
custerion --title "Blade Runner (1982)" --dry-run
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

Note: for maximum compatibility in live tests, set `LLM_LIVE_TEST_MODEL` to the
exact model/provider string you want to validate through LiteLLM.

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
