from __future__ import annotations

import os
import uuid
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone

from custerion_collection.artifact_builder import build_deep_dive_artifact
from custerion_collection.config import model_fallback_names, model_name
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


MODEL_OVERRIDE_KEYS = [
    "MODEL_NAME",
    "MODEL_NAME_CREATIVE_DIRECTOR",
    "MODEL_NAME_PERSONAL_MATCHMAKER",
    "MODEL_NAME_CULTURAL_HISTORIAN",
    "MODEL_NAME_TECHNICAL_DIRECTOR",
    "MODEL_NAME_INDUSTRIAL_ANALYST",
    "MODEL_NAME_FOLLOW_UP_CURATOR",
    "MODEL_NAME_SCRIPT_EDITOR",
]


@contextmanager
def _temporary_model_override(model: str):
    previous = {key: os.environ.get(key) for key in MODEL_OVERRIDE_KEYS}
    for key in MODEL_OVERRIDE_KEYS:
        os.environ[key] = model
    try:
        yield
    finally:
        for key, value in previous.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value


def _unique_models(primary: str, fallbacks: list[str]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for candidate in [primary, *fallbacks]:
        if not candidate or candidate in seen:
            continue
        seen.add(candidate)
        result.append(candidate)
    return result


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

        primary_model = model_name()
        attempt_models = _unique_models(primary_model, model_fallback_names())
        provider_error_names = {
            "AuthenticationError",
            "BadRequestError",
            "RateLimitError",
            "ServiceUnavailableError",
        }
        provider_failures: list[str] = []
        markdown = ""

        try:
            for index, attempt_model in enumerate(attempt_models):
                with _temporary_model_override(attempt_model):
                    crew = build_deep_dive_crew(
                        title=selected_title,
                        suggestion_mode=suggestion_mode,
                        process_mode_override=process_mode_override,
                    )
                    try:
                        markdown = str(crew.kickoff())
                        if index > 0:
                            warnings.append(f"Fallback model used: {attempt_model}")
                        break
                    except Exception as exc:
                        if exc.__class__.__name__ in provider_error_names:
                            provider_failures.append(f"{attempt_model}: {exc}")
                            continue
                        raise
            else:
                raise ValueError(
                    "LLM provider request failed for all configured models: "
                    + " | ".join(provider_failures)
                )
        except ImportError as exc:
            raise ValueError(
                "Unable to initialize LLM provider for this model configuration. "
                "Use a supported provider-style model name (for example 'openai/<model>') "
                "or install LiteLLM ('pip install litellm'). "
                "You can also run with dry-run enabled while configuring providers."
            ) from exc
        except Exception as exc:
            if exc.__class__.__name__ in provider_error_names:
                raise ValueError(f"LLM provider request failed: {exc}") from exc
            raise

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
