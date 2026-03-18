from __future__ import annotations

import os
import unittest
from unittest.mock import patch

from custerion_collection.identity import resolve_canonical_film_identity


class TestIdentityResolution(unittest.TestCase):
    @patch.dict(os.environ, {}, clear=True)
    def test_requires_tmdb_key(self) -> None:
        result = resolve_canonical_film_identity("Blade Runner (1982)")
        self.assertIsNone(result.identity)
        self.assertIn("TMDB_API_KEY", result.error or "")

    @patch.dict(os.environ, {"TMDB_API_KEY": "token"}, clear=True)
    @patch("custerion_collection.identity._http_get_json")
    def test_reports_ambiguity_without_year(self, mock_get_json) -> None:
        mock_get_json.return_value = (
            {
                "results": [
                    {"id": 1, "title": "Dune", "release_date": "1984-12-01"},
                    {"id": 2, "title": "Dune", "release_date": "2021-10-22"},
                ]
            },
            None,
        )

        result = resolve_canonical_film_identity("Dune")

        self.assertIsNone(result.identity)
        self.assertIn("Ambiguous title", result.error or "")

    @patch.dict(os.environ, {"TMDB_API_KEY": "token"}, clear=True)
    @patch("custerion_collection.identity._http_get_json")
    def test_resolves_with_year_and_builds_canonical_id(self, mock_get_json) -> None:
        mock_get_json.side_effect = [
            (
                {
                    "results": [
                        {"id": 2, "title": "Dune", "release_date": "2021-10-22"},
                    ]
                },
                None,
            ),
            (
                {
                    "id": 2,
                    "title": "Dune",
                    "release_date": "2021-10-22",
                    "runtime": 155,
                    "original_language": "en",
                    "credits": {"crew": [{"job": "Director", "name": "Denis Villeneuve"}]},
                    "external_ids": {"imdb_id": "tt1160419"},
                },
                None,
            ),
        ]

        result = resolve_canonical_film_identity("Dune (2021)")

        self.assertIsNone(result.error)
        self.assertIsNotNone(result.identity)
        assert result.identity is not None
        self.assertEqual(result.identity.canonical_id, "tmdb:movie:2")
        self.assertEqual(result.identity.year, 2021)
        self.assertEqual(result.identity.external_ids.get("imdb"), "tt1160419")


if __name__ == "__main__":
    unittest.main()
