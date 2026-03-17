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


if __name__ == "__main__":
    unittest.main()
