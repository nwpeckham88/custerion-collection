from __future__ import annotations

import unittest
from unittest.mock import patch

from custerion_collection.identity import IdentityResolutionResult
from custerion_collection.service import execute_deep_dive


class TestService(unittest.TestCase):
    @patch("custerion_collection.service.resolve_canonical_film_identity")
    @patch("custerion_collection.crew.build_deep_dive_crew")
    def test_execute_deep_dive_surfaces_provider_setup_error(
        self,
        mock_build_crew,
        mock_resolve_identity,
    ) -> None:
        mock_resolve_identity.return_value = IdentityResolutionResult(identity=None, error=None)
        mock_build_crew.side_effect = ImportError("provider init failed")

        with self.assertRaises(ValueError) as error:
            execute_deep_dive(
                title="The Red Shoes (1948)",
                suggestion_mode=False,
                process_mode_override="hierarchical",
                dry_run=False,
            )

        self.assertIn("Unable to initialize LLM provider", str(error.exception))

    @patch("custerion_collection.service.resolve_canonical_film_identity")
    @patch("custerion_collection.crew.build_deep_dive_crew")
    @patch("custerion_collection.service.model_fallback_names")
    def test_execute_deep_dive_surfaces_provider_runtime_bad_request(
        self,
        mock_fallbacks,
        mock_build_crew,
        mock_resolve_identity,
    ) -> None:
        class BadRequestError(Exception):
            pass

        mock_fallbacks.return_value = []
        mock_resolve_identity.return_value = IdentityResolutionResult(identity=None, error=None)

        mock_crew = unittest.mock.Mock()
        mock_crew.kickoff.side_effect = BadRequestError("invalid model id")
        mock_build_crew.return_value = mock_crew

        with self.assertRaises(ValueError) as error:
            execute_deep_dive(
                title="The Red Shoes (1948)",
                suggestion_mode=False,
                process_mode_override="hierarchical",
                dry_run=False,
            )

        self.assertIn("LLM provider request failed for all configured models", str(error.exception))

    @patch("custerion_collection.service.resolve_canonical_film_identity")
    @patch("custerion_collection.crew.build_deep_dive_crew")
    @patch("custerion_collection.service.model_fallback_names")
    def test_execute_deep_dive_uses_fallback_model_after_provider_failure(
        self,
        mock_fallbacks,
        mock_build_crew,
        mock_resolve_identity,
    ) -> None:
        class BadRequestError(Exception):
            pass

        mock_fallbacks.return_value = ["openrouter/qwen/qwen3-next-80b-a3b-instruct:free"]
        mock_resolve_identity.return_value = IdentityResolutionResult(identity=None, error=None)

        first_crew = unittest.mock.Mock()
        first_crew.kickoff.side_effect = BadRequestError("model unavailable")
        second_crew = unittest.mock.Mock()
        second_crew.kickoff.return_value = "## Personalized Intro\nFallback succeeded"
        mock_build_crew.side_effect = [first_crew, second_crew]

        result = execute_deep_dive(
            title="The Red Shoes (1948)",
            suggestion_mode=False,
            process_mode_override="hierarchical",
            dry_run=False,
        )

        self.assertIn(result.status, {"success", "degraded"})
        self.assertIn("Fallback succeeded", result.markdown)
        self.assertIn("Fallback model used", " ".join(result.warnings))


if __name__ == "__main__":
    unittest.main()
