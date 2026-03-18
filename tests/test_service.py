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
                title="Blade Runner (1982) (1948)",
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
                title="Blade Runner (1982) (1948)",
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
        second_crew.kickoff.return_value = (
            "## Personalized Intro\n"
            "This suggestion is tailored for viewers who value emotionally expressive filmmaking with strong visual language.\n\n"
            "## History\n"
            "The film sits at the crossroads of post-war studio production and modern art-film sensibilities. "
            "Reference: https://en.wikipedia.org/wiki/The_Red_Shoes_(film)\n\n"
            "## Craft\n"
            "Its color design and choreography-driven editing remain widely studied, with archival documentation available via "
            "the BFI and restoration notes. Reference: https://www.bfi.org.uk/\n\n"
            "## Industry\n"
            "The release and long-tail impact demonstrate how prestige distribution can transform a film's canon status. "
            "Reference: https://www.themoviedb.org/movie/19542\n\n"
            "## Notable Lore\n"
            "Production stories around rehearsal discipline and camera blocking have become part of the film's lasting lore.\n"
        )
        mock_build_crew.side_effect = [first_crew, second_crew]

        result = execute_deep_dive(
            title="Blade Runner (1982) (1948)",
            suggestion_mode=False,
            process_mode_override="hierarchical",
            dry_run=False,
        )

        self.assertIn(result.status, {"success", "degraded"})
        self.assertIn("## History", result.markdown)
        self.assertIn("Fallback model used", " ".join(result.warnings))

    @patch("custerion_collection.service.resolve_canonical_film_identity")
    @patch("custerion_collection.crew.build_deep_dive_crew")
    @patch("custerion_collection.service.model_fallback_names")
    def test_execute_deep_dive_rejects_trivial_output(
        self,
        mock_fallbacks,
        mock_build_crew,
        mock_resolve_identity,
    ) -> None:
        mock_fallbacks.return_value = []
        mock_resolve_identity.return_value = IdentityResolutionResult(identity=None, error=None)

        crew = unittest.mock.Mock()
        crew.kickoff.return_value = "## Personalized Intro\nFallback succeeded"
        mock_build_crew.return_value = crew

        with self.assertRaises(ValueError) as error:
            execute_deep_dive(
                title="Blade Runner (1982) (1948)",
                suggestion_mode=False,
                process_mode_override="hierarchical",
                dry_run=False,
            )

        self.assertIn("quality gates", str(error.exception))

    @patch("custerion_collection.service.resolve_canonical_film_identity")
    @patch("custerion_collection.crew.build_deep_dive_crew")
    @patch("custerion_collection.service.model_fallback_names")
    def test_execute_deep_dive_rejects_placeholder_source_urls(
        self,
        mock_fallbacks,
        mock_build_crew,
        mock_resolve_identity,
    ) -> None:
        mock_fallbacks.return_value = []
        mock_resolve_identity.return_value = IdentityResolutionResult(identity=None, error=None)

        crew = unittest.mock.Mock()
        crew.kickoff.return_value = (
            "## Personalized Intro\n"
            "A rich and detailed perspective on the film and its legacy.\n\n"
            "## History\n"
            "Production context with placeholder source: https://example.com/fake\n\n"
            "## Craft\n"
            "Visual analysis grounded in concrete observations and style breakdown.\n\n"
            "## Industry\n"
            "Box-office and reception context with long-term impact framing.\n\n"
            "## Notable Lore\n"
            "Anecdotes and lasting influence discussion for genre history.\n"
        )
        mock_build_crew.return_value = crew

        with self.assertRaises(ValueError) as error:
            execute_deep_dive(
                title="Blade Runner (1982)",
                suggestion_mode=False,
                process_mode_override="hierarchical",
                dry_run=False,
            )

        self.assertIn("placeholder source URLs", str(error.exception))


if __name__ == "__main__":
    unittest.main()
