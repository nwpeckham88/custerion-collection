from __future__ import annotations

import os
import json
from pathlib import Path

from dotenv import load_dotenv


load_dotenv()


def sync_provider_env() -> None:
    """Normalize provider env vars for LiteLLM compatibility.

    This allows users to set OpenRouter using OpenAI-compatible variables while
    still supporting LiteLLM provider-specific auth lookup.
    """

    openai_key = os.getenv("OPENAI_API_KEY", "").strip()
    openrouter_key = os.getenv("OPENROUTER_API_KEY", "").strip()
    if openai_key and not openrouter_key:
        os.environ["OPENROUTER_API_KEY"] = openai_key

    openai_base = os.getenv("OPENAI_BASE_URL", "").strip()
    openrouter_base = os.getenv("OPENROUTER_API_BASE", "").strip()
    if openai_base and "openrouter.ai" in openai_base and not openrouter_base:
        os.environ["OPENROUTER_API_BASE"] = openai_base


sync_provider_env()


def validate_critical_env_vars() -> None:
    """Fail fast on critical provider env misconfiguration.

    Validation is intentionally strict for OpenRouter usage because ambiguous
    auth/base-url failures are otherwise surfaced deep inside model calls.
    """

    openai_key = os.getenv("OPENAI_API_KEY", "").strip()
    openrouter_key = os.getenv("OPENROUTER_API_KEY", "").strip()
    openai_base = os.getenv("OPENAI_BASE_URL", "").strip()
    openrouter_base = os.getenv("OPENROUTER_API_BASE", "").strip()

    openai_base_lower = openai_base.lower()
    openrouter_base_lower = openrouter_base.lower()
    using_openrouter_base = "openrouter.ai" in openai_base_lower or "openrouter.ai" in openrouter_base_lower
    using_openrouter_key = openai_key.startswith("sk-or-v1-") or openrouter_key.startswith("sk-or-v1-")

    if openai_base and not (openai_base.startswith("http://") or openai_base.startswith("https://")):
        raise ValueError(
            "Invalid OPENAI_BASE_URL: must start with http:// or https://"
        )

    if using_openrouter_key and not using_openrouter_base:
        raise ValueError(
            "OpenRouter key detected, but OpenRouter base URL is missing. "
            "Set OPENAI_BASE_URL=https://openrouter.ai/api/v1"
        )

    if using_openrouter_base and not (openai_key or openrouter_key):
        raise ValueError(
            "OpenRouter is configured, but no API key was provided. "
            "Set OPENAI_API_KEY (or OPENROUTER_API_KEY)."
        )


def data_dir() -> Path:
    """Return local data directory used for persisted artifacts."""
    raw = os.getenv("DATA_DIR", "./data")
    return Path(raw).resolve()


def model_name(role: str | None = None) -> str:
    """Return model name, with optional role-specific override.

    Example override key: MODEL_NAME_TECHNICAL_DIRECTOR
    """
    if role:
        key = "MODEL_NAME_" + "_".join(role.upper().strip().split())
        override = os.getenv(key, "").strip()
        if override:
            return override
    return os.getenv("MODEL_NAME", "gpt-4o-mini")


def model_fallback_names() -> list[str]:
    """Return ordered fallback models from MODEL_FALLBACKS.

    Expected format: comma-separated model slugs.
    """

    raw = os.getenv("MODEL_FALLBACKS", "")
    if not raw.strip():
        return []

    seen: set[str] = set()
    result: list[str] = []
    for part in raw.split(","):
        candidate = part.strip()
        if not candidate or candidate in seen:
            continue
        seen.add(candidate)
        result.append(candidate)
    return result


def html_report_model_name() -> str | None:
    """Return optional model override for HTML report generation.

    When unset, HTML rendering falls back to deterministic local formatting.
    """

    raw = os.getenv("MODEL_NAME_HTML_REPORTER", "").strip()
    return raw or None


def process_mode(override: str | None = None) -> str:
    """Return orchestration mode; allowed values are hierarchical or sequential."""
    raw_value = override if override is not None else os.getenv("PROCESS_MODE", "hierarchical")
    raw = raw_value.strip().lower()
    if raw in {"hierarchical", "sequential"}:
        return raw
    return "hierarchical"


def commentary_planner_model_name() -> str:
    """Return model for commentary planning, preferring a smart model override."""

    explicit = os.getenv("MODEL_NAME_COMMENTARY_PLANNER", "").strip()
    if explicit:
        return explicit

    # Prefer high-capability model slots before generic fallback.
    editor_model = os.getenv("MODEL_NAME_SCRIPT_EDITOR", "").strip()
    if editor_model:
        return editor_model

    return model_name()


def commentary_planning_goal() -> str:
    """Return app-controlled objective for subtitle+report commentary planning."""

    return os.getenv(
        "COMMENTARY_PLANNING_GOAL",
        (
            "Generate a spoiler-aware audio commentary track from subtitle cues and the report. "
            "Use the report as the source of insights, align each insight to the first subtitle context "
            "that supports it, add a short reveal delay, keep pacing smooth, and avoid clustering dense facts. "
            "Prefer narrative clarity and emotional flow over trivia density."
        ),
    ).strip()


def openrouter_extra_headers() -> dict[str, str]:
    """Return optional OpenRouter attribution headers for direct API calls."""

    headers: dict[str, str] = {}
    referer = os.getenv("OPENROUTER_HTTP_REFERER", "").strip()
    title = os.getenv("OPENROUTER_APP_TITLE", "").strip()
    if referer:
        headers["HTTP-Referer"] = referer
    if title:
        headers["X-OpenRouter-Title"] = title
    return headers


def openrouter_provider_preferences() -> dict[str, object] | None:
    """Return optional OpenRouter provider routing object from JSON env."""

    raw = os.getenv("OPENROUTER_PROVIDER_PREFERENCES_JSON", "").strip()
    if not raw:
        return None

    try:
        parsed = json.loads(raw)
    except Exception:
        return None

    if isinstance(parsed, dict):
        return parsed
    return None
