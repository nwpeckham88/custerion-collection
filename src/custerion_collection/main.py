from __future__ import annotations

import argparse
import uuid
from datetime import datetime, timezone

from custerion_collection.artifact_builder import build_deep_dive_artifact
from custerion_collection.identity import resolve_canonical_film_identity
from custerion_collection.models import DeepDiveArtifact, RunDiagnostics
from custerion_collection.schema import export_deep_dive_schema
from custerion_collection.storage import write_artifact_bundle, write_markdown_artifact, write_run_diagnostics


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Generate a film deep-dive with CrewAI.")
    parser.add_argument("--title", type=str, help="Film title to deep-dive")
    parser.add_argument(
        "--suggest",
        action="store_true",
        help="Use suggestion mode when no specific title is requested",
    )
    parser.add_argument(
        "--export-schema",
        action="store_true",
        help="Export DeepDiveArtifact JSON schema and exit",
    )
    parser.add_argument(
        "--schema-output",
        type=str,
        default=None,
        help="Optional schema output path used with --export-schema",
    )
    parser.add_argument(
        "--process-mode",
        type=str,
        choices=["hierarchical", "sequential"],
        default=None,
        help="Optional per-run process mode override",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Skip CrewAI kickoff and generate a deterministic sample artifact",
    )
    return parser


def run() -> None:
    args = _parser().parse_args()

    if args.export_schema:
        schema_path = export_deep_dive_schema(output_path=args.schema_output)
        print(f"Schema saved to: {schema_path}")
        return

    if not args.title and not args.suggest and not args.dry_run:
        raise SystemExit("Provide --title or use --suggest")

    title = args.title or "Suggested Film"
    resolved_identity = None
    run_id = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S") + "-" + uuid.uuid4().hex[:8]
    started_at = datetime.now(timezone.utc)
    warnings: list[str] = []
    status = "success"

    # Resolve explicit title requests to a canonical ID before synthesis.
    if args.title and not args.dry_run:
        resolution = resolve_canonical_film_identity(args.title)
        if resolution.error:
            finished_at = datetime.now(timezone.utc)
            diagnostics_path = write_run_diagnostics(
                RunDiagnostics(
                    run_id=run_id,
                    title=title,
                    suggestion_mode=args.suggest,
                    status="failed",
                    started_at=started_at,
                    finished_at=finished_at,
                    duration_ms=max(0, int((finished_at - started_at).total_seconds() * 1000)),
                    warnings=[resolution.error],
                    source_count=0,
                    citation_coverage_ratio=0.0,
                )
            )
            print(f"Run diagnostics saved to: {diagnostics_path}")
            raise SystemExit(resolution.error)

        resolved_identity = resolution.identity
        if resolved_identity is not None:
            title = resolved_identity.title

    if args.dry_run:
        warnings.append("Dry-run mode enabled: CrewAI kickoff skipped.")
        output = _dry_run_markdown(title=title, suggestion_mode=args.suggest)
    else:
        from custerion_collection.crew import build_deep_dive_crew

        crew = build_deep_dive_crew(
            title=title,
            suggestion_mode=args.suggest,
            process_mode_override=args.process_mode,
        )
        try:
            result = crew.kickoff()
        except Exception as exc:
            finished_at = datetime.now(timezone.utc)
            diagnostics_path = write_run_diagnostics(
                RunDiagnostics(
                    run_id=run_id,
                    title=title,
                    suggestion_mode=args.suggest,
                    status="failed",
                    started_at=started_at,
                    finished_at=finished_at,
                    duration_ms=max(0, int((finished_at - started_at).total_seconds() * 1000)),
                    warnings=[f"Crew run failed: {exc}"],
                    source_count=0,
                    citation_coverage_ratio=0.0,
                )
            )
            print(f"Run diagnostics saved to: {diagnostics_path}")
            raise

        output = str(result)
    source_count = output.count("http://") + output.count("https://")
    try:
        artifact = build_deep_dive_artifact(
            title=title,
            markdown=output,
            film_identity=resolved_identity,
        )
        markdown_path, json_path = write_artifact_bundle(
            title=title,
            markdown=output,
            artifact=artifact,
        )
        print(f"Deep-dive markdown saved to: {markdown_path}")
        print(f"Deep-dive artifact saved to: {json_path}")

        coverage_ratio = _compute_citation_coverage(artifact)
    except Exception as exc:
        status = "degraded"
        warnings.append(f"Structured artifact export failed: {exc}")
        path = write_markdown_artifact(title=title, content=output)
        print(f"Deep-dive saved to: {path}")
        print(f"Warning: structured artifact export failed: {exc}")
        coverage_ratio = 0.0

    finished_at = datetime.now(timezone.utc)
    diagnostics_path = write_run_diagnostics(
        RunDiagnostics(
            run_id=run_id,
            title=title,
            suggestion_mode=args.suggest,
            status=status,
            started_at=started_at,
            finished_at=finished_at,
            duration_ms=max(0, int((finished_at - started_at).total_seconds() * 1000)),
            warnings=warnings,
            source_count=source_count,
            citation_coverage_ratio=coverage_ratio,
        )
    )
    print(f"Run diagnostics saved to: {diagnostics_path}")


def _compute_citation_coverage(artifact: DeepDiveArtifact) -> float:
    """Estimate citation coverage using available section and citation counts."""
    section_count = max(1, len(artifact.sections))
    citation_count = len(artifact.citations)
    return min(1.0, citation_count / section_count)


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


if __name__ == "__main__":
    run()
