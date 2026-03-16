from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

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


def list_recent_artifacts(limit: int = 20) -> list[dict[str, Any]]:
    artifacts = ensure_data_dirs()

    grouped: dict[str, dict[str, Path | None]] = {}

    for markdown_path in artifacts.glob("*.md"):
        grouped.setdefault(markdown_path.stem, {"markdown": None, "json": None})["markdown"] = markdown_path

    for json_path in artifacts.glob("*.json"):
        grouped.setdefault(json_path.stem, {"markdown": None, "json": None})["json"] = json_path

    ordered = sorted(
        grouped.items(),
        key=lambda item: _entry_mtime(item[1]),
        reverse=True,
    )

    items: list[dict[str, Any]] = []
    for stem, paths in ordered[: max(1, limit)]:
        markdown_path = paths["markdown"]
        json_path = paths["json"]

        title = _extract_title_from_artifact_json(json_path)
        if not title:
            title = _title_from_stem(stem)

        items.append(
            {
                "title": title,
                "slug": stem,
                "markdown_path": str(markdown_path) if markdown_path else None,
                "artifact_json_path": str(json_path) if json_path else None,
                "updated_at": datetime.fromtimestamp(
                    _entry_mtime(paths),
                    tz=timezone.utc,
                ).isoformat(),
            }
        )

    return items


def _entry_mtime(entry: dict[str, Path | None]) -> float:
    markdown_path = entry["markdown"]
    json_path = entry["json"]

    markdown_mtime = markdown_path.stat().st_mtime if markdown_path else 0.0
    json_mtime = json_path.stat().st_mtime if json_path else 0.0
    return max(markdown_mtime, json_mtime)


def _extract_title_from_artifact_json(json_path: Path | None) -> str | None:
    if not json_path:
        return None

    try:
        payload = json.loads(json_path.read_text(encoding="utf-8"))
    except Exception:
        return None

    if not isinstance(payload, dict):
        return None

    film = payload.get("film")
    if not isinstance(film, dict):
        return None

    title = film.get("title")
    return title if isinstance(title, str) and title.strip() else None


def _title_from_stem(stem: str) -> str:
    # Drop trailing run timestamp when file naming follows slug-YYYYMMDD-HHMMSS.
    title_slug = re.sub(r"-\d{8}-\d{6}$", "", stem)
    words = [part for part in title_slug.split("-") if part]
    if not words:
        return "Untitled"
    return " ".join(word.capitalize() for word in words)


def _slugify(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return slug or "untitled"
