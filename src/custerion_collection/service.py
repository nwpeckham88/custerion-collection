from __future__ import annotations

import os
import uuid
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Callable

from custerion_collection.artifact_builder import build_deep_dive_artifact
from custerion_collection.config import html_report_model_name, model_fallback_names, model_name
from custerion_collection.identity import resolve_canonical_film_identity
from custerion_collection.models import RunDiagnostics
from custerion_collection.suggestion import suggest_film_title
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
    html_path: str | None = None


MODEL_OVERRIDE_KEYS = [
    "MODEL_NAME",
    "MODEL_NAME_CREATIVE_DIRECTOR",
    "MODEL_NAME_PERSONAL_MATCHMAKER",
    "MODEL_NAME_CULTURAL_HISTORIAN",
    "MODEL_NAME_TECHNICAL_DIRECTOR",
    "MODEL_NAME_INDUSTRIAL_ANALYST",
    "MODEL_NAME_TRIVIA_RESEARCHER",
    "MODEL_NAME_FOLLOW_UP_CURATOR",
    "MODEL_NAME_SCRIPT_EDITOR",
]


MIN_MARKDOWN_CHARS = 500
MIN_CITATION_COVERAGE = 0.5


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


def _render_html_report(markdown: str, selected_title: str) -> tuple[str | None, str | None]:
    model = html_report_model_name()
    if not model:
        return None, None

    try:
        from litellm import completion  # type: ignore

        response = completion(
            model=model,
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You are an expert front-end report formatter. "
                        "Return only full HTML for a standalone report page with embedded CSS. "
                        "Style should be elegant, restrained, and highly readable. "
                        "Use the movie as aesthetic inspiration in a subtle way: palette, typography, mood cues, and spacing. "
                        "Do not create gimmicky or themed UI elements that distract from reading."
                    ),
                },
                {
                    "role": "user",
                    "content": (
                        f"Format this deep-dive markdown into elegant HTML for '{selected_title}'. "
                        "Preserve factual content and headings. Include responsive CSS. "
                        "Make the visual language feel 'colored by the movie' but reserved and editorial. "
                        "Prioritize typography, hierarchy, comfortable line length, and subtle accents over decorative effects.\n\n"
                        + markdown
                    ),
                },
            ],
            temperature=0.3,
        )
        content = ""
        if isinstance(response, dict):
            content = (response.get("choices", [{}])[0].get("message", {}).get("content", "") or "")
        else:
            choices = getattr(response, "choices", [])
            if choices:
                message = getattr(choices[0], "message", None)
                if message is not None:
                    content = getattr(message, "content", "") or ""
        html = content.strip()
        if not html.lower().startswith("<!doctype html") and "<html" not in html.lower():
            return None, f"MODEL_NAME_HTML_REPORTER response was not valid HTML: {model}"
        return html, None
    except Exception as exc:
        return None, f"MODEL_NAME_HTML_REPORTER failed ({model}): {exc}"


def execute_deep_dive(
    *,
    title: str | None,
    suggestion_mode: bool,
    process_mode_override: str | None,
    dry_run: bool,
    progress_callback: Callable[[str, int], None] | None = None,
) -> DeepDiveRunResult:
    def emit(stage: str, progress: int) -> None:
        if progress_callback is None:
            return
        clamped = max(0, min(progress, 100))
        progress_callback(stage, clamped)

    emit("Initializing run", 5)

    if not title and not suggestion_mode and not dry_run:
        raise ValueError("Provide a title, enable suggestion mode, or use dry-run.")

    resolved_identity = None
    selected_title = title or "Suggested Film"
    run_id = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S") + "-" + uuid.uuid4().hex[:8]
    started_at = datetime.now(timezone.utc)
    warnings: list[str] = []
    status = "success"

    if suggestion_mode and not title and not dry_run:
        emit("Selecting suggested film", 10)
        selected_title, suggestion_warnings = suggest_film_title()
        warnings.extend(suggestion_warnings)

    if selected_title and not dry_run:
        emit("Resolving film identity", 15)
        resolution = resolve_canonical_film_identity(selected_title)
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
        emit("Generating dry-run output", 55)
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
                    emit("Building crew", 35)
                    crew = build_deep_dive_crew(
                        title=selected_title,
                        suggestion_mode=suggestion_mode,
                        process_mode_override=process_mode_override,
                    )
                    try:
                        emit("Running agent workflow", 60)
                        markdown = str(crew.kickoff())
                        emit("Synthesizing output", 78)
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
    html_path: str | None = None
    emit("Persisting artifacts", 88)

    artifact = build_deep_dive_artifact(
        title=selected_title,
        markdown=markdown,
        film_identity=resolved_identity,
    )
    quality_issues = _quality_issues(
        markdown=markdown,
        section_count=len(artifact.sections),
        non_placeholder_section_count=sum(
            1
            for section in artifact.sections
            if "limited confirmed detail" not in section.content.lower()
        ),
        citation_count=len(artifact.citations),
    )
    if quality_issues and not dry_run:
        diagnostics_path = _write_failed_diagnostics(
            run_id=run_id,
            title=selected_title,
            suggestion_mode=suggestion_mode,
            started_at=started_at,
            warning="; ".join(quality_issues),
        )
        raise ValueError(
            "Generated output failed quality gates: "
            + "; ".join(quality_issues)
            + f" (diagnostics: {diagnostics_path})"
        )

    try:
        html_content, html_warning = _render_html_report(markdown=markdown, selected_title=selected_title)
        if html_warning:
            warnings.append(html_warning)
        markdown_file, json_file, html_file = write_artifact_bundle(
            title=selected_title,
            markdown=markdown,
            artifact=artifact,
            html_content=html_content,
        )
        markdown_path = str(markdown_file)
        artifact_json_path = str(json_file)
        html_path = str(html_file)
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
        html_path=html_path,
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


def _quality_issues(
    *,
    markdown: str,
    section_count: int,
    non_placeholder_section_count: int,
    citation_count: int,
) -> list[str]:
    issues: list[str] = []
    stripped = markdown.strip()

    if len(stripped) < MIN_MARKDOWN_CHARS:
        issues.append(
            f"content too short ({len(stripped)} chars; minimum {MIN_MARKDOWN_CHARS})"
        )

    if section_count > 0 and non_placeholder_section_count < 2:
        issues.append("insufficient substantive sections (need at least 2 non-placeholder sections)")

    coverage = _compute_citation_coverage(section_count=section_count, citation_count=citation_count)
    if coverage < MIN_CITATION_COVERAGE:
        issues.append(
            "citation coverage below threshold "
            f"({coverage:.2f}; minimum {MIN_CITATION_COVERAGE:.2f})"
        )

    return issues


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
