from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path

from custerion_collection.config import data_dir
from custerion_collection.models import DeepDiveArtifact, RunDiagnostics


def ensure_data_dirs() -> Path:
    base = data_dir()
    artifacts = base / "artifacts"
    artifacts.mkdir(parents=True, exist_ok=True)
    return artifacts


def ensure_diagnostics_dir() -> Path:
    base = data_dir()
    diagnostics = base / "diagnostics"
    diagnostics.mkdir(parents=True, exist_ok=True)
    return diagnostics


def write_markdown_artifact(title: str, content: str) -> Path:
    artifacts = ensure_data_dirs()
    slug = _slugify(title)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    path = artifacts / f"{slug}-{stamp}.md"
    path.write_text(content, encoding="utf-8")
    return path


def write_artifact_bundle(title: str, markdown: str, artifact: DeepDiveArtifact) -> tuple[Path, Path]:
    artifacts = ensure_data_dirs()
    slug = _slugify(title)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")

    markdown_path = artifacts / f"{slug}-{stamp}.md"
    json_path = artifacts / f"{slug}-{stamp}.json"

    markdown_path.write_text(markdown, encoding="utf-8")
    json_path.write_text(
        json.dumps(artifact.model_dump(mode="json"), indent=2, sort_keys=True),
        encoding="utf-8",
    )
    return markdown_path, json_path


def write_run_diagnostics(diagnostics: RunDiagnostics) -> Path:
    target_dir = ensure_diagnostics_dir()
    file_path = target_dir / f"{diagnostics.run_id}.json"
    file_path.write_text(
        json.dumps(diagnostics.model_dump(mode="json"), indent=2, sort_keys=True),
        encoding="utf-8",
    )
    return file_path


def _slugify(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return slug or "untitled"
