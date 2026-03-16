from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv


load_dotenv()


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
