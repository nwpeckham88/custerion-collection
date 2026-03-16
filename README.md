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

Use `--suggest` instead of `--title` to run suggestion mode.

## Notes
- This is a scaffold: external retrieval adapters are placeholders.
- Generated artifacts are written under `data/artifacts/`.
- Follow-Up Media is intentionally scoped to avoid feature creep.
