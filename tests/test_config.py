from __future__ import annotations

import os
import unittest
from unittest.mock import patch

from custerion_collection.config import model_name, process_mode


class TestConfig(unittest.TestCase):
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
