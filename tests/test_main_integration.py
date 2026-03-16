from __future__ import annotations

import tempfile
import unittest
from argparse import Namespace
from pathlib import Path
from unittest.mock import MagicMock, patch

from custerion_collection.identity import IdentityResolutionResult
from custerion_collection.main import run


class TestMainIntegration(unittest.TestCase):
    @patch("custerion_collection.main._parser")
    @patch("custerion_collection.main.write_run_diagnostics")
    @patch("custerion_collection.main.write_artifact_bundle")
    @patch("custerion_collection.main.build_deep_dive_artifact")
    @patch("custerion_collection.main.resolve_canonical_film_identity")
    @patch("custerion_collection.crew.build_deep_dive_crew")
    def test_run_success_persists_bundle_and_diagnostics(
        self,
        mock_build_crew,
        mock_resolve_identity,
        mock_build_artifact,
        mock_write_bundle,
        mock_write_diagnostics,
        mock_parser,
    ) -> None:
        mock_parser.return_value.parse_args.return_value = Namespace(
            title="The Red Shoes",
            suggest=False,
            export_schema=False,
            schema_output=None,
            process_mode="sequential",
            dry_run=False,
        )

        mock_crew = MagicMock()
        mock_crew.kickoff.return_value = "## History\nContext https://example.com"
        mock_build_crew.return_value = mock_crew
        mock_resolve_identity.return_value = IdentityResolutionResult(identity=None, error=None)

        artifact = MagicMock()
        artifact.sections = [MagicMock(), MagicMock()]
        artifact.citations = [MagicMock()]
        mock_build_artifact.return_value = artifact

        with tempfile.TemporaryDirectory() as tmp:
            mock_write_bundle.return_value = (Path(tmp) / "out.md", Path(tmp) / "out.json")
            mock_write_diagnostics.return_value = Path(tmp) / "diag.json"

            run()

        self.assertTrue(mock_write_bundle.called)
        self.assertTrue(mock_write_diagnostics.called)
        self.assertEqual(mock_write_diagnostics.call_args.args[0].status, "success")
        self.assertEqual(mock_build_crew.call_args.kwargs["process_mode_override"], "sequential")

    @patch("custerion_collection.main._parser")
    @patch("custerion_collection.main.write_run_diagnostics")
    @patch("custerion_collection.main.write_markdown_artifact")
    @patch("custerion_collection.main.build_deep_dive_artifact")
    @patch("custerion_collection.main.resolve_canonical_film_identity")
    @patch("custerion_collection.crew.build_deep_dive_crew")
    def test_run_degraded_when_structured_export_fails(
        self,
        mock_build_crew,
        mock_resolve_identity,
        mock_build_artifact,
        mock_write_markdown,
        mock_write_diagnostics,
        mock_parser,
    ) -> None:
        mock_parser.return_value.parse_args.return_value = Namespace(
            title="The Red Shoes",
            suggest=False,
            export_schema=False,
            schema_output=None,
            process_mode=None,
            dry_run=False,
        )

        mock_crew = MagicMock()
        mock_crew.kickoff.return_value = "freeform output"
        mock_build_crew.return_value = mock_crew
        mock_resolve_identity.return_value = IdentityResolutionResult(identity=None, error=None)
        mock_build_artifact.side_effect = ValueError("bad shape")

        with tempfile.TemporaryDirectory() as tmp:
            mock_write_markdown.return_value = Path(tmp) / "out.md"
            mock_write_diagnostics.return_value = Path(tmp) / "diag.json"
            run()

        self.assertTrue(mock_write_markdown.called)
        self.assertEqual(mock_write_diagnostics.call_args.args[0].status, "degraded")

    @patch("custerion_collection.main._parser")
    @patch("custerion_collection.main.write_run_diagnostics")
    @patch("custerion_collection.main.resolve_canonical_film_identity")
    @patch("custerion_collection.crew.build_deep_dive_crew")
    def test_run_failed_when_crew_raises(
        self,
        mock_build_crew,
        mock_resolve_identity,
        mock_write_diagnostics,
        mock_parser,
    ) -> None:
        mock_parser.return_value.parse_args.return_value = Namespace(
            title="The Red Shoes",
            suggest=False,
            export_schema=False,
            schema_output=None,
            process_mode=None,
            dry_run=False,
        )

        mock_crew = MagicMock()
        mock_crew.kickoff.side_effect = RuntimeError("boom")
        mock_build_crew.return_value = mock_crew
        mock_resolve_identity.return_value = IdentityResolutionResult(identity=None, error=None)

        with tempfile.TemporaryDirectory() as tmp:
            mock_write_diagnostics.return_value = Path(tmp) / "diag.json"
            with self.assertRaises(RuntimeError):
                run()

        self.assertEqual(mock_write_diagnostics.call_args.args[0].status, "failed")

    @patch("custerion_collection.main._parser")
    @patch("custerion_collection.main.write_run_diagnostics")
    @patch("custerion_collection.main.write_artifact_bundle")
    @patch("custerion_collection.main.build_deep_dive_artifact")
    @patch("custerion_collection.crew.build_deep_dive_crew")
    def test_run_dry_run_skips_crew_kickoff(
        self,
        mock_build_crew,
        mock_build_artifact,
        mock_write_bundle,
        mock_write_diagnostics,
        mock_parser,
    ) -> None:
        mock_parser.return_value.parse_args.return_value = Namespace(
            title="The Red Shoes",
            suggest=False,
            export_schema=False,
            schema_output=None,
            process_mode="hierarchical",
            dry_run=True,
        )

        artifact = MagicMock()
        artifact.sections = [MagicMock()]
        artifact.citations = [MagicMock()]
        mock_build_artifact.return_value = artifact

        with tempfile.TemporaryDirectory() as tmp:
            mock_write_bundle.return_value = (Path(tmp) / "out.md", Path(tmp) / "out.json")
            mock_write_diagnostics.return_value = Path(tmp) / "diag.json"
            run()

        self.assertFalse(mock_build_crew.called)
        self.assertTrue(mock_write_bundle.called)
        diagnostics = mock_write_diagnostics.call_args.args[0]
        self.assertEqual(diagnostics.status, "success")
        self.assertTrue(any("Dry-run mode enabled" in warning for warning in diagnostics.warnings))

    @patch("custerion_collection.main._parser")
    @patch("custerion_collection.main.write_run_diagnostics")
    @patch("custerion_collection.main.resolve_canonical_film_identity")
    def test_run_fails_early_on_ambiguous_title(
        self,
        mock_resolve_identity,
        mock_write_diagnostics,
        mock_parser,
    ) -> None:
        mock_parser.return_value.parse_args.return_value = Namespace(
            title="Dune",
            suggest=False,
            export_schema=False,
            schema_output=None,
            process_mode=None,
            dry_run=False,
        )
        mock_resolve_identity.return_value = IdentityResolutionResult(
            identity=None,
            error="Ambiguous title 'Dune'. Provide year.",
        )

        with tempfile.TemporaryDirectory() as tmp:
            mock_write_diagnostics.return_value = Path(tmp) / "diag.json"
            with self.assertRaises(SystemExit):
                run()

        self.assertEqual(mock_write_diagnostics.call_args.args[0].status, "failed")


if __name__ == "__main__":
    unittest.main()
