from __future__ import annotations

import os
import unittest
from unittest.mock import patch

from custerion_collection.config import html_report_model_name, model_name, process_mode, sync_provider_env


class TestConfig(unittest.TestCase):
    @patch.dict(os.environ, {"OPENAI_API_KEY": "test-key"}, clear=True)
    def test_sync_provider_env_sets_openrouter_key(self) -> None:
        sync_provider_env()
        self.assertEqual(os.environ.get("OPENROUTER_API_KEY"), "test-key")

    @patch.dict(
        os.environ,
        {
            "OPENAI_BASE_URL": "https://openrouter.ai/api/v1",
            "OPENAI_API_KEY": "test-key",
        },
        clear=True,
    )
    def test_sync_provider_env_sets_openrouter_base(self) -> None:
        sync_provider_env()
        self.assertEqual(os.environ.get("OPENROUTER_API_BASE"), "https://openrouter.ai/api/v1")

    @patch.dict(os.environ, {}, clear=True)
    def test_model_name_defaults(self) -> None:
        self.assertEqual(model_name(), "gpt-4o-mini")

    @patch.dict(os.environ, {"MODEL_NAME": "openrouter/meta-llama/llama-3.1-70b-instruct"}, clear=True)
    def test_model_name_uses_default_env(self) -> None:
        self.assertEqual(model_name(), "openrouter/meta-llama/llama-3.1-70b-instruct")

    @patch.dict(
        os.environ,
        {
            "MODEL_NAME": "openrouter/meta-llama/llama-3.1-8b-instruct",
            "MODEL_NAME_TECHNICAL_DIRECTOR": "openrouter/openai/gpt-4.1-mini",
        },
        clear=True,
    )
    def test_model_name_role_override(self) -> None:
        self.assertEqual(model_name(role="Technical Director"), "openrouter/openai/gpt-4.1-mini")
        self.assertEqual(model_name(role="Cultural Historian"), "openrouter/meta-llama/llama-3.1-8b-instruct")

    @patch.dict(os.environ, {}, clear=True)
    def test_html_report_model_name_defaults_none(self) -> None:
        self.assertIsNone(html_report_model_name())

    @patch.dict(os.environ, {"MODEL_NAME_HTML_REPORTER": "openrouter/qwen/qwen3-next-80b-a3b-instruct:free"}, clear=True)
    def test_html_report_model_name_reads_override(self) -> None:
        self.assertEqual(
            html_report_model_name(),
            "openrouter/qwen/qwen3-next-80b-a3b-instruct:free",
        )

    @patch.dict(os.environ, {}, clear=True)
    def test_process_mode_defaults_hierarchical(self) -> None:
        self.assertEqual(process_mode(), "hierarchical")

    @patch.dict(os.environ, {"PROCESS_MODE": "sequential"}, clear=True)
    def test_process_mode_allows_sequential(self) -> None:
        self.assertEqual(process_mode(), "sequential")

    @patch.dict(os.environ, {"PROCESS_MODE": "invalid"}, clear=True)
    def test_process_mode_invalid_falls_back(self) -> None:
        self.assertEqual(process_mode(), "hierarchical")

    @patch.dict(os.environ, {"PROCESS_MODE": "hierarchical"}, clear=True)
    def test_process_mode_override_wins(self) -> None:
        self.assertEqual(process_mode(override="sequential"), "sequential")

    @patch.dict(os.environ, {"PROCESS_MODE": "sequential"}, clear=True)
    def test_process_mode_invalid_override_falls_back(self) -> None:
        self.assertEqual(process_mode(override="invalid"), "hierarchical")


if __name__ == "__main__":
    unittest.main()
