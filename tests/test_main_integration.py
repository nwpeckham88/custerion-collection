from __future__ import annotations

import unittest
from argparse import Namespace
from unittest.mock import call, patch

from custerion_collection.main import run
from custerion_collection.service import DeepDiveRunResult


class TestMainIntegration(unittest.TestCase):
    @patch("custerion_collection.main._parser")
    @patch("custerion_collection.main.execute_deep_dive")
    @patch("builtins.print")
    def test_run_success_prints_outputs(
        self,
        mock_print,
        mock_execute_deep_dive,
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
        mock_execute_deep_dive.return_value = DeepDiveRunResult(
            title="The Red Shoes",
            markdown="## History\nContext https://example.com",
            status="success",
            warnings=["sample warning"],
            diagnostics_path="/tmp/diag.json",
            markdown_path="/tmp/out.md",
            artifact_json_path="/tmp/out.json",
        )

        run()

        mock_execute_deep_dive.assert_called_once_with(
            title="The Red Shoes",
            suggestion_mode=False,
            process_mode_override="sequential",
            dry_run=False,
        )
        mock_print.assert_has_calls(
            [
                call("Deep-dive markdown saved to: /tmp/out.md"),
                call("Deep-dive artifact saved to: /tmp/out.json"),
                call("Warning: sample warning"),
                call("Run diagnostics saved to: /tmp/diag.json"),
            ]
        )

    @patch("custerion_collection.main._parser")
    @patch("custerion_collection.main.execute_deep_dive")
    def test_run_exits_when_service_raises_value_error(
        self,
        mock_execute_deep_dive,
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
        mock_execute_deep_dive.side_effect = ValueError("Ambiguous title")

        with self.assertRaises(SystemExit) as error:
            run()

        self.assertEqual(str(error.exception), "Ambiguous title")

    @patch("custerion_collection.main._parser")
    @patch("builtins.print")
    @patch("custerion_collection.main.export_deep_dive_schema")
    @patch("custerion_collection.main.execute_deep_dive")
    def test_run_export_schema_path_exits_early(
        self,
        mock_execute_deep_dive,
        mock_export_schema,
        mock_print,
        mock_parser,
    ) -> None:
        mock_parser.return_value.parse_args.return_value = Namespace(
            title=None,
            suggest=False,
            export_schema=True,
            schema_output="/tmp/schema.json",
            process_mode=None,
            dry_run=False,
        )
        mock_export_schema.return_value = "/tmp/schema.json"

        run()

        mock_export_schema.assert_called_once_with(output_path="/tmp/schema.json")
        mock_execute_deep_dive.assert_not_called()
        mock_print.assert_called_once_with("Schema saved to: /tmp/schema.json")

    @patch("custerion_collection.main._parser")
    @patch("custerion_collection.main.execute_deep_dive")
    def test_run_dry_run_delegates_to_service(
        self,
        mock_execute_deep_dive,
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
        mock_execute_deep_dive.return_value = DeepDiveRunResult(
            title="The Red Shoes",
            markdown="dry run",
            status="success",
            warnings=["Dry-run mode enabled: CrewAI kickoff skipped."],
            diagnostics_path="/tmp/diag.json",
            markdown_path="/tmp/out.md",
            artifact_json_path="/tmp/out.json",
        )

        run()

        mock_execute_deep_dive.assert_called_once_with(
            title="The Red Shoes",
            suggestion_mode=False,
            process_mode_override="hierarchical",
            dry_run=True,
        )

    @patch("custerion_collection.main._parser")
    def test_run_requires_title_or_suggest_or_dry_run(self, mock_parser) -> None:
        mock_parser.return_value.parse_args.return_value = Namespace(
            title=None,
            suggest=False,
            export_schema=False,
            schema_output=None,
            process_mode=None,
            dry_run=False,
        )
        with self.assertRaises(SystemExit) as error:
            run()

        self.assertEqual(str(error.exception), "Provide --title or use --suggest")


if __name__ == "__main__":
    unittest.main()
