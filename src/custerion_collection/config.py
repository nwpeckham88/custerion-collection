from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv


load_dotenv()


def data_dir() -> Path:
    """Return local data directory used for persisted artifacts."""
    raw = os.getenv("DATA_DIR", "./data")
    return Path(raw).resolve()


def model_name() -> str:
    """Return default model name for CrewAI LLM configuration."""
    return os.getenv("MODEL_NAME", "gpt-4o-mini")
