from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime, timezone

from custerion_collection.artifact_builder import build_deep_dive_artifact
from custerion_collection.identity import resolve_canonical_film_identity
from custerion_collection.models import RunDiagnostics
from custerion_collection.storage import write_artifact_bundle, write_markdown_artifact, write_run_diagnostics


@dataclass(slots=True)
class DeepDiveRunResult:
    title: str
    markdown: str
    status: str
    warnings: list[str]
    diagnostics_path: str
    markdown_path: str | None = None
    artifact_json_path: str | None = None


def execute_deep_dive(
    *,
    title: str | None,
    suggestion_mode: bool,
    process_mode_override: str | None,
    dry_run: bool,
) -> DeepDiveRunResult:
    if not title and not suggestion_mode and not dry_run:
        raise ValueError("Provide a title, enable suggestion mode, or use dry-run.")

    resolved_identity = None
    selected_title = title or "Suggested Film"
    run_id = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S") + "-" + uuid.uuid4().hex[:8]
    started_at = datetime.now(timezone.utc)
    warnings: list[str] = []
    status = "success"

    if title and not dry_run:
        resolution = resolve_canonical_film_identity(title)
        if resolution.error:
            diagnostics_path = _write_failed_diagnostics(
                run_id=run_id,
                title=selected_title,
                suggestion_mode=suggestion_mode,
                started_at=started_at,
                warning=resolution.error,
            )
            raise ValueError(f"{resolution.error} (diagnostics: {diagnostics_path})")

        resolved_identity = resolution.identity
        if resolved_identity is not None:
            selected_title = resolved_identity.title

    if dry_run:
        warnings.append("Dry-run mode enabled: CrewAI kickoff skipped.")
        markdown = _dry_run_markdown(title=selected_title, suggestion_mode=suggestion_mode)
    else:
        from custerion_collection.crew import build_deep_dive_crew

        crew = build_deep_dive_crew(
            title=selected_title,
            suggestion_mode=suggestion_mode,
            process_mode_override=process_mode_override,
        )
        markdown = str(crew.kickoff())

    source_count = markdown.count("http://") + markdown.count("https://")
    markdown_path: str | None = None
    artifact_json_path: str | None = None

    try:
        artifact = build_deep_dive_artifact(
            title=selected_title,
            markdown=markdown,
            film_identity=resolved_identity,
        )
        markdown_file, json_file = write_artifact_bundle(
            title=selected_title,
            markdown=markdown,
            artifact=artifact,
        )
        markdown_path = str(markdown_file)
        artifact_json_path = str(json_file)
        coverage_ratio = _compute_citation_coverage(len(artifact.sections), len(artifact.citations))
    except Exception as exc:
        status = "degraded"
        warnings.append(f"Structured artifact export failed: {exc}")
        markdown_file = write_markdown_artifact(title=selected_title, content=markdown)
        markdown_path = str(markdown_file)
        coverage_ratio = 0.0

    finished_at = datetime.now(timezone.utc)
    diagnostics_path = write_run_diagnostics(
        RunDiagnostics(
            run_id=run_id,
            title=selected_title,
            suggestion_mode=suggestion_mode,
            status=status,
            started_at=started_at,
            finished_at=finished_at,
            duration_ms=max(0, int((finished_at - started_at).total_seconds() * 1000)),
            warnings=warnings,
            source_count=source_count,
            citation_coverage_ratio=coverage_ratio,
        )
    )

    return DeepDiveRunResult(
        title=selected_title,
        markdown=markdown,
        status=status,
        warnings=warnings,
        diagnostics_path=str(diagnostics_path),
        markdown_path=markdown_path,
        artifact_json_path=artifact_json_path,
    )


def _write_failed_diagnostics(
    *,
    run_id: str,
    title: str,
    suggestion_mode: bool,
    started_at: datetime,
    warning: str,
) -> str:
    finished_at = datetime.now(timezone.utc)
    diagnostics_path = write_run_diagnostics(
        RunDiagnostics(
            run_id=run_id,
            title=title,
            suggestion_mode=suggestion_mode,
            status="failed",
            started_at=started_at,
            finished_at=finished_at,
            duration_ms=max(0, int((finished_at - started_at).total_seconds() * 1000)),
            warnings=[warning],
            source_count=0,
            citation_coverage_ratio=0.0,
        )
    )
    return str(diagnostics_path)


def _compute_citation_coverage(section_count: int, citation_count: int) -> float:
    normalized_sections = max(1, section_count)
    return min(1.0, citation_count / normalized_sections)


def _dry_run_markdown(title: str, suggestion_mode: bool) -> str:
    mode_text = "suggestion mode" if suggestion_mode else "explicit title mode"
    return (
        f"## Personalized Intro\n"
        f"This deterministic dry-run demonstrates artifact generation for '{title}' in {mode_text}.\n\n"
        "## History\n"
        "Dry-run historical context is intentionally synthetic and marked for smoke testing.\n\n"
        "## Craft\n"
        "Dry-run craft section verifies stable section parsing and confidence handling.\n\n"
        "## Industry\n"
        "Dry-run industry section validates diagnostics and persistence flow.\n\n"
        "## Notable Lore\n"
        "Dry-run lore avoids factual claims and exists to validate formatting contracts.\n\n"
        "## What To Watch Next\n"
        "- Dry Run Companion Film\n\n"
        "## Known Unknowns\n"
        "- This output does not include real retrieval evidence.\n\n"
        "## Follow-Up Media\n"
        "1. Example article: https://example.com/reference\n"
    )
