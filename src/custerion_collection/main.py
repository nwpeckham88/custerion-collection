from __future__ import annotations

import argparse

from custerion_collection.schema import export_deep_dive_schema
from custerion_collection.service import execute_deep_dive


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

    try:
        result = execute_deep_dive(
            title=args.title,
            suggestion_mode=args.suggest,
            process_mode_override=args.process_mode,
            dry_run=args.dry_run,
        )
    except ValueError as exc:
        raise SystemExit(str(exc)) from exc

    if result.markdown_path:
        print(f"Deep-dive markdown saved to: {result.markdown_path}")
    if result.artifact_json_path:
        print(f"Deep-dive artifact saved to: {result.artifact_json_path}")
    if result.html_path:
        print(f"Deep-dive HTML report saved to: {result.html_path}")

    for warning in result.warnings:
        print(f"Warning: {warning}")

    print(f"Run diagnostics saved to: {result.diagnostics_path}")


if __name__ == "__main__":
    run()
