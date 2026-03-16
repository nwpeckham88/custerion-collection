from __future__ import annotations

import argparse

from custerion_collection.crew import build_deep_dive_crew
from custerion_collection.storage import write_markdown_artifact


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Generate a film deep-dive with CrewAI.")
    parser.add_argument("--title", type=str, help="Film title to deep-dive")
    parser.add_argument(
        "--suggest",
        action="store_true",
        help="Use suggestion mode when no specific title is requested",
    )
    return parser


def run() -> None:
    args = _parser().parse_args()

    if not args.title and not args.suggest:
        raise SystemExit("Provide --title or use --suggest")

    title = args.title or "Suggested Film"
    crew = build_deep_dive_crew(title=title, suggestion_mode=args.suggest)
    result = crew.kickoff()

    output = str(result)
    path = write_markdown_artifact(title=title, content=output)
    print(f"Deep-dive saved to: {path}")


if __name__ == "__main__":
    run()
