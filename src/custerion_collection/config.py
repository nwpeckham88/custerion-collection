from __future__ import annotations

import os
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


def process_mode(override: str | None = None) -> str:
    """Return orchestration mode; allowed values are hierarchical or sequential."""
    raw_value = override if override is not None else os.getenv("PROCESS_MODE", "hierarchical")
    raw = raw_value.strip().lower()
    if raw in {"hierarchical", "sequential"}:
        return raw
    return "hierarchical"
