from __future__ import annotations

import json
import re
from html import escape
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


def write_artifact_bundle(
    title: str,
    markdown: str,
    artifact: DeepDiveArtifact,
    html_content: str | None = None,
) -> tuple[Path, Path, Path]:
    artifacts = ensure_data_dirs()
    slug = _slugify(title)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")

    markdown_path = artifacts / f"{slug}-{stamp}.md"
    json_path = artifacts / f"{slug}-{stamp}.json"
    html_path = artifacts / f"{slug}-{stamp}.html"

    markdown_path.write_text(markdown, encoding="utf-8")
    json_path.write_text(
        json.dumps(artifact.model_dump(mode="json"), indent=2, sort_keys=True),
        encoding="utf-8",
    )
    html_path.write_text(html_content or _render_artifact_html(artifact), encoding="utf-8")
    return markdown_path, json_path, html_path


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
    tts_audio_dir = (artifacts / "tts").resolve()

    grouped: dict[str, dict[str, Path | None]] = {}

    for markdown_path in artifacts.glob("*.md"):
        grouped.setdefault(markdown_path.stem, {"markdown": None, "json": None, "html": None, "tts_audio": None})[
            "markdown"
        ] = markdown_path

    for json_path in artifacts.glob("*.json"):
        grouped.setdefault(json_path.stem, {"markdown": None, "json": None, "html": None, "tts_audio": None})["json"] = json_path

    for html_path in artifacts.glob("*.html"):
        grouped.setdefault(html_path.stem, {"markdown": None, "json": None, "html": None, "tts_audio": None})["html"] = html_path

    if tts_audio_dir.exists():
        for stem, paths in grouped.items():
            tts_candidates = sorted(
                list(tts_audio_dir.glob(f"{stem}-*.wav")) + list(tts_audio_dir.glob(f"{stem}-*.mp3")),
                key=lambda path: path.stat().st_mtime,
                reverse=True,
            )
            if tts_candidates:
                paths["tts_audio"] = tts_candidates[0]

    ordered = sorted(
        grouped.items(),
        key=lambda item: _entry_mtime(item[1]),
        reverse=True,
    )

    items: list[dict[str, Any]] = []
    for stem, paths in ordered[: max(1, limit)]:
        markdown_path = paths["markdown"]
        json_path = paths["json"]
        html_path = paths["html"]
        tts_audio_path = paths["tts_audio"]

        title = _extract_title_from_artifact_json(json_path)
        if not title:
            title = _title_from_stem(stem)

        items.append(
            {
                "title": title,
                "slug": stem,
                "markdown_path": str(markdown_path) if markdown_path else None,
                "artifact_json_path": str(json_path) if json_path else None,
                "html_path": str(html_path) if html_path else None,
                "tts_audio_path": str(tts_audio_path) if tts_audio_path else None,
                "updated_at": datetime.fromtimestamp(
                    _entry_mtime(paths),
                    tz=timezone.utc,
                ).isoformat(),
            }
        )

    return items


def latest_html_artifact_for_slug(slug: str) -> Path | None:
    artifacts = ensure_data_dirs()
    candidates = sorted(
        artifacts.glob(f"{slug}*.html"),
        key=lambda path: path.stat().st_mtime,
        reverse=True,
    )
    if not candidates:
        return None
    return candidates[0]


def latest_markdown_artifact_for_slug(slug: str) -> Path | None:
    artifacts = ensure_data_dirs()
    candidates = sorted(
        artifacts.glob(f"{slug}*.md"),
        key=lambda path: path.stat().st_mtime,
        reverse=True,
    )
    if not candidates:
        return None
    return candidates[0]


def latest_tts_audio_artifact_for_slug(slug: str) -> Path | None:
    artifacts = ensure_data_dirs()
    tts_audio_dir = (artifacts / "tts").resolve()
    if not tts_audio_dir.exists():
        return None

    candidates = sorted(
        list(tts_audio_dir.glob(f"{slug}-*.wav")) + list(tts_audio_dir.glob(f"{slug}-*.mp3")),
        key=lambda path: path.stat().st_mtime,
        reverse=True,
    )
    if not candidates:
        return None
    return candidates[0]


def latest_json_artifact_for_slug(slug: str) -> Path | None:
    artifacts = ensure_data_dirs()
    candidates = sorted(
        artifacts.glob(f"{slug}*.json"),
        key=lambda path: path.stat().st_mtime,
        reverse=True,
    )
    if not candidates:
        return None
    return candidates[0]


def latest_subtitle_artifact_for_slug(slug: str) -> Path | None:
    artifacts = ensure_data_dirs()
    candidates = sorted(
        artifacts.glob(f"{slug}*.srt"),
        key=lambda path: path.stat().st_mtime,
        reverse=True,
    )
    if not candidates:
        return None
    return candidates[0]


def latest_commentary_plan_artifact_for_slug(slug: str) -> Path | None:
    artifacts = ensure_data_dirs()
    candidates = sorted(
        artifacts.glob(f"{slug}*.commentary-plan.json"),
        key=lambda path: path.stat().st_mtime,
        reverse=True,
    )
    if not candidates:
        return None
    return candidates[0]


def artifact_title_for_slug(slug: str) -> str:
    json_path = latest_json_artifact_for_slug(slug)
    title = _extract_title_from_artifact_json(json_path)
    if title:
        return title
    return _title_from_stem(slug)


def upsert_html_artifact_for_slug(slug: str, html_content: str) -> Path:
    artifacts = ensure_data_dirs()

    candidates: list[Path] = []
    markdown_path = latest_markdown_artifact_for_slug(slug)
    json_path = latest_json_artifact_for_slug(slug)
    html_path = latest_html_artifact_for_slug(slug)

    if markdown_path:
        candidates.append(markdown_path)
    if json_path:
        candidates.append(json_path)
    if html_path:
        candidates.append(html_path)

    if candidates:
        stem = max(candidates, key=lambda path: path.stat().st_mtime).stem
    else:
        stem = slug

    target = artifacts / f"{stem}.html"
    target.write_text(html_content, encoding="utf-8")
    return target


def upsert_subtitle_artifact_for_slug(slug: str, subtitle_text: str) -> Path:
    artifacts = ensure_data_dirs()

    candidates: list[Path] = []
    markdown_path = latest_markdown_artifact_for_slug(slug)
    json_path = latest_json_artifact_for_slug(slug)
    html_path = latest_html_artifact_for_slug(slug)
    subtitle_path = latest_subtitle_artifact_for_slug(slug)

    if markdown_path:
        candidates.append(markdown_path)
    if json_path:
        candidates.append(json_path)
    if html_path:
        candidates.append(html_path)
    if subtitle_path:
        candidates.append(subtitle_path)

    if candidates:
        stem = max(candidates, key=lambda path: path.stat().st_mtime).stem
    else:
        stem = slug

    target = artifacts / f"{stem}.srt"
    target.write_text(subtitle_text, encoding="utf-8")
    return target


def upsert_commentary_plan_artifact_for_slug(slug: str, payload: dict[str, Any]) -> Path:
    artifacts = ensure_data_dirs()

    candidates: list[Path] = []
    markdown_path = latest_markdown_artifact_for_slug(slug)
    json_path = latest_json_artifact_for_slug(slug)
    html_path = latest_html_artifact_for_slug(slug)
    subtitle_path = latest_subtitle_artifact_for_slug(slug)
    commentary_plan_path = latest_commentary_plan_artifact_for_slug(slug)

    if markdown_path:
        candidates.append(markdown_path)
    if json_path:
        candidates.append(json_path)
    if html_path:
        candidates.append(html_path)
    if subtitle_path:
        candidates.append(subtitle_path)
    if commentary_plan_path:
        candidates.append(commentary_plan_path)

    if candidates:
        stem = max(candidates, key=lambda path: path.stat().st_mtime).stem
    else:
        stem = slug

    # Normalize stem if this call is rewriting an existing commentary plan file.
    stem = stem.removesuffix(".commentary-plan")
    target = artifacts / f"{stem}.commentary-plan.json"
    target.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    return target


def load_artifact_for_slug(slug: str) -> DeepDiveArtifact | None:
    json_path = latest_json_artifact_for_slug(slug)
    if json_path is None or not json_path.exists():
        return None

    try:
        payload = json.loads(json_path.read_text(encoding="utf-8"))
        return DeepDiveArtifact.model_validate(payload)
    except Exception:
        return None


def _entry_mtime(entry: dict[str, Path | None]) -> float:
    markdown_path = entry["markdown"]
    json_path = entry["json"]
    html_path = entry["html"]
    tts_audio_path = entry["tts_audio"]

    markdown_mtime = markdown_path.stat().st_mtime if markdown_path else 0.0
    json_mtime = json_path.stat().st_mtime if json_path else 0.0
    html_mtime = html_path.stat().st_mtime if html_path else 0.0
    tts_audio_mtime = tts_audio_path.stat().st_mtime if tts_audio_path else 0.0
    return max(markdown_mtime, json_mtime, html_mtime, tts_audio_mtime)


def _render_artifact_html(artifact: DeepDiveArtifact) -> str:
    sections_html = "".join(
        f"<section><h2>{escape(section.name)}</h2><p>{escape(section.content)}</p>"
        "</section>"
        for section in artifact.sections
    )
    watch_next_html = "".join(f"<li>{escape(item)}</li>" for item in artifact.watch_next)
    unknowns_html = "".join(f"<li>{escape(item)}</li>" for item in artifact.known_unknowns)
    media_html = "".join(
        "<li>"
        f"<strong>{escape(item.title)}</strong> "
        f"<span class='kind'>[{escape(item.kind)}]</span>"
        f"<p>{escape(item.rationale)}</p>"
        + (
            f"<a href='{escape(str(item.url))}' target='_blank' rel='noopener noreferrer'>{escape(str(item.url))}</a>"
            if item.url
            else ""
        )
        + "</li>"
        for item in artifact.follow_up_media
    )
    citations_html = "".join(
        "<li>"
        f"<strong>{escape(citation.provider)}</strong>: {escape(citation.claim_ref)}"
        + (
            f" <a href='{escape(str(citation.url))}' target='_blank' rel='noopener noreferrer'>source</a>"
            if citation.url
            else ""
        )
        + "</li>"
        for citation in artifact.citations
    )

    return (
        "<!doctype html>\n"
        "<html lang='en'>\n"
        "<head>\n"
        "  <meta charset='utf-8' />\n"
        "  <meta name='viewport' content='width=device-width, initial-scale=1' />\n"
        f"  <title>{escape(artifact.film.title)} Deep Dive</title>\n"
        "  <style>\n"
        "    :root { color-scheme: light; --ink:#1f2937; --muted:#6b7280; --bg:#f4efe6; --card:#ffffff; --accent:#0f766e; --line:#e5e7eb; }\n"
        "    * { box-sizing:border-box; }\n"
        "    body { margin:0; font-family:'Georgia','Times New Roman',serif; color:var(--ink); background:linear-gradient(135deg,#f4efe6,#f3f7fb); }\n"
        "    .wrap { max-width:920px; margin:32px auto; padding:0 16px 48px; }\n"
        "    .hero { background:var(--card); border:1px solid var(--line); border-radius:18px; padding:28px; box-shadow:0 10px 30px rgba(15,23,42,.08); }\n"
        "    h1 { margin:0 0 8px; font-size:2.2rem; line-height:1.15; }\n"
        "    .meta { color:var(--muted); font-family:'Trebuchet MS',sans-serif; }\n"
        "    .intro { margin-top:14px; font-size:1.1rem; }\n"
        "    section { margin-top:18px; background:var(--card); border:1px solid var(--line); border-radius:14px; padding:20px; }\n"
        "    h2 { margin:0 0 10px; font-size:1.35rem; color:var(--accent); font-family:'Trebuchet MS',sans-serif; }\n"
        "    p { margin:0 0 8px; line-height:1.7; }\n"
        "    ul { margin:8px 0 0 20px; }\n"
        "    li { margin:6px 0; line-height:1.6; }\n"
        "    .kind { color:var(--muted); font-size:.92rem; font-family:'Trebuchet MS',sans-serif; }\n"
        "    a { color:#0b4f9c; }\n"
        "    @media (max-width:700px){ h1{font-size:1.7rem;} .hero, section{padding:16px;} }\n"
        "  </style>\n"
        "</head>\n"
        "<body>\n"
        "  <div class='wrap'>\n"
        "    <article class='hero'>\n"
        f"      <h1>{escape(artifact.film.title)} ({artifact.film.year})</h1>\n"
        f"      <div class='meta'>Canonical ID: {escape(artifact.film.canonical_id)}</div>\n"
        f"      <p class='intro'>{escape(artifact.personalized_intro)}</p>\n"
        "    </article>\n"
        f"    {sections_html}\n"
        "    <section><h2>What To Watch Next</h2><ul>"
        f"{watch_next_html or '<li>None listed</li>'}"
        "</ul></section>\n"
        "    <section><h2>Open Questions</h2><ul>"
        f"{unknowns_html or '<li>None listed</li>'}"
        "</ul></section>\n"
        "    <section><h2>Follow-Up Media</h2><ul>"
        f"{media_html or '<li>None listed</li>'}"
        "</ul></section>\n"
        "    <section><h2>Citations</h2><ul>"
        f"{citations_html or '<li>No citations captured</li>'}"
        "</ul></section>\n"
        "  </div>\n"
        "</body>\n"
        "</html>\n"
    )


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
