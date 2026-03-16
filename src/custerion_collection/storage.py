from __future__ import annotations

from datetime import datetime
from pathlib import Path

from custerion_collection.config import data_dir


def ensure_data_dirs() -> Path:
    base = data_dir()
    artifacts = base / "artifacts"
    artifacts.mkdir(parents=True, exist_ok=True)
    return artifacts


def write_markdown_artifact(title: str, content: str) -> Path:
    artifacts = ensure_data_dirs()
    slug = "-".join(title.lower().split())
    stamp = datetime.utcnow().strftime("%Y%m%d-%H%M%S")
    path = artifacts / f"{slug}-{stamp}.md"
    path.write_text(content, encoding="utf-8")
    return path
