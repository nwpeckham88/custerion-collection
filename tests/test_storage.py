from __future__ import annotations

import os
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from custerion_collection.models import DeepDiveArtifact, DeepDiveSection, FilmIdentity, RunDiagnostics
from custerion_collection.storage import write_artifact_bundle, write_markdown_artifact, write_run_diagnostics


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

    def test_write_artifact_bundle_creates_markdown_and_json(self) -> None:
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

            markdown_path, json_path = write_artifact_bundle(
                title="Test Film",
                markdown="content",
                artifact=artifact,
            )

            self.assertTrue(markdown_path.exists())
            self.assertTrue(json_path.exists())
            self.assertEqual(markdown_path.suffix, ".md")
            self.assertEqual(json_path.suffix, ".json")
            self.assertIn('"film"', json_path.read_text(encoding="utf-8"))

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


if __name__ == "__main__":
    unittest.main()
