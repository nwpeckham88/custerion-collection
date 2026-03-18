from __future__ import annotations

import os
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from custerion_collection.models import CommentarySegment, DeepDiveArtifact, DeepDiveSection, FilmIdentity, RunDiagnostics
from custerion_collection.storage import (
    list_recent_artifacts,
    latest_subtitle_artifact_for_slug,
    load_artifact_for_slug,
    upsert_subtitle_artifact_for_slug,
    write_artifact_bundle,
    write_markdown_artifact,
    write_run_diagnostics,
)


class TestStorage(unittest.TestCase):
    def test_write_markdown_artifact_creates_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            os.environ["DATA_DIR"] = tmp
            path = write_markdown_artifact("Test Film", "content")

            self.assertTrue(path.exists())
            self.assertTrue(path.name.startswith("test-film-"))
            self.assertEqual(path.read_text(encoding="utf-8"), "content")

            artifacts_dir = Path(tmp) / "artifacts"
            self.assertEqual(path.parent, artifacts_dir.resolve())

    def test_write_artifact_bundle_creates_markdown_json_and_html(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            os.environ["DATA_DIR"] = tmp
            artifact = DeepDiveArtifact(
                film=FilmIdentity(title="Test Film", year=2020, canonical_id="local:test-film:2020"),
                personalized_intro="intro",
                sections=[DeepDiveSection(name="History", content="x", confidence=0.7)],
                watch_next=[],
                known_unknowns=[],
                follow_up_media=[],
                citations=[],
                created_at=datetime.now(timezone.utc),
            )

            markdown_path, json_path, html_path = write_artifact_bundle(
                title="Test Film",
                markdown="content",
                artifact=artifact,
                html_content=None,
            )

            self.assertTrue(markdown_path.exists())
            self.assertTrue(json_path.exists())
            self.assertTrue(html_path.exists())
            self.assertEqual(markdown_path.suffix, ".md")
            self.assertEqual(json_path.suffix, ".json")
            self.assertEqual(html_path.suffix, ".html")
            self.assertIn('"film"', json_path.read_text(encoding="utf-8"))
            self.assertIn("<html", html_path.read_text(encoding="utf-8"))

    def test_write_run_diagnostics_creates_json(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            os.environ["DATA_DIR"] = tmp
            diagnostics = RunDiagnostics(
                run_id="run-123",
                title="Test Film",
                suggestion_mode=False,
                status="success",
                started_at=datetime.now(timezone.utc),
                finished_at=datetime.now(timezone.utc),
                duration_ms=12,
                warnings=[],
                source_count=3,
                citation_coverage_ratio=0.75,
            )

            path = write_run_diagnostics(diagnostics)

            self.assertTrue(path.exists())
            self.assertEqual(path.suffix, ".json")
            self.assertIn('"run_id": "run-123"', path.read_text(encoding="utf-8"))

    def test_list_recent_artifacts_includes_bundle_and_markdown(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            os.environ["DATA_DIR"] = tmp

            artifact = DeepDiveArtifact(
                film=FilmIdentity(title="The Red Shoes", year=1948, canonical_id="local:the-red-shoes:1948"),
                personalized_intro="intro",
                sections=[DeepDiveSection(name="History", content="x", confidence=0.7)],
                watch_next=[],
                known_unknowns=[],
                follow_up_media=[],
                citations=[],
                created_at=datetime.now(timezone.utc),
            )

            write_artifact_bundle(title="The Red Shoes", markdown="bundle", artifact=artifact)
            write_markdown_artifact("Only Markdown", "markdown-only")

            items = list_recent_artifacts(limit=10)

            self.assertGreaterEqual(len(items), 2)
            titles = {item["title"] for item in items}
            self.assertIn("The Red Shoes", titles)
            self.assertIn("Only Markdown", titles)
            red_shoes = next(item for item in items if item["title"] == "The Red Shoes")
            self.assertTrue(red_shoes["html_path"]) 

    def test_list_recent_artifacts_honors_limit(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            os.environ["DATA_DIR"] = tmp

            write_markdown_artifact("Film One", "content")
            write_markdown_artifact("Film Two", "content")

            items = list_recent_artifacts(limit=1)

            self.assertEqual(len(items), 1)

    def test_load_artifact_for_slug_includes_commentary(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            os.environ["DATA_DIR"] = tmp
            artifact = DeepDiveArtifact(
                film=FilmIdentity(title="Test Film", year=2020, canonical_id="local:test-film:2020"),
                personalized_intro="intro",
                sections=[DeepDiveSection(name="History", content="x", confidence=0.7)],
                commentary_segments=[
                    CommentarySegment(
                        order_index=0,
                        timestamp_ms=30000,
                        scene_label="Opening",
                        commentary="Visual tone established.",
                    )
                ],
                commentary_mode="timed",
                watch_next=[],
                known_unknowns=[],
                follow_up_media=[],
                citations=[],
                created_at=datetime.now(timezone.utc),
            )

            write_artifact_bundle(title="Test Film", markdown="content", artifact=artifact)
            loaded = load_artifact_for_slug("test-film")

            self.assertIsNotNone(loaded)
            assert loaded is not None
            self.assertEqual(len(loaded.commentary_segments), 1)
            self.assertEqual(loaded.commentary_segments[0].timestamp_ms, 30000)

    def test_upsert_subtitle_artifact_for_slug_creates_srt(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            os.environ["DATA_DIR"] = tmp
            artifact = DeepDiveArtifact(
                film=FilmIdentity(title="Test Film", year=2020, canonical_id="local:test-film:2020"),
                personalized_intro="intro",
                sections=[DeepDiveSection(name="History", content="x", confidence=0.7)],
                watch_next=[],
                known_unknowns=[],
                follow_up_media=[],
                citations=[],
                created_at=datetime.now(timezone.utc),
            )
            write_artifact_bundle(title="Test Film", markdown="content", artifact=artifact)

            path = upsert_subtitle_artifact_for_slug(
                slug="test-film",
                subtitle_text="1\n00:00:02,000 --> 00:00:03,000\nLine\n\n",
            )

            self.assertTrue(path.exists())
            self.assertEqual(path.suffix, ".srt")
            self.assertIn("00:00:02,000", path.read_text(encoding="utf-8"))
            latest = latest_subtitle_artifact_for_slug("test-film")
            self.assertIsNotNone(latest)


if __name__ == "__main__":
    unittest.main()
