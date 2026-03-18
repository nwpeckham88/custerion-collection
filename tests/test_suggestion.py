from __future__ import annotations

import os
import unittest
from unittest.mock import patch

from custerion_collection.suggestion import suggest_film_title


class TestSuggestion(unittest.TestCase):
    @patch.dict(os.environ, {"TMDB_API_KEY": "token"}, clear=True)
    @patch("custerion_collection.suggestion._recent_jellyfin_titles")
    @patch("custerion_collection.suggestion._http_get_json")
    def test_suggest_film_title_prefers_tmdb_trending(
        self,
        mock_get_json,
        mock_recent,
    ) -> None:
        mock_recent.return_value = ["Dune"]
        mock_get_json.return_value = (
            {
                "results": [
                    {"title": "Dune", "release_date": "2021-10-22", "vote_count": 1000, "popularity": 99.9},
                    {"title": "Blade Runner (1982)", "release_date": "1948-09-06", "vote_count": 400, "popularity": 25.0},
                ]
            },
            None,
        )

        title, warnings = suggest_film_title()

        self.assertEqual(title, "Blade Runner (1982) (1948)")
        self.assertEqual(warnings, [])

    @patch.dict(os.environ, {}, clear=True)
    @patch("custerion_collection.suggestion._recent_jellyfin_titles")
    def test_suggest_film_title_uses_jellyfin_fallback(self, mock_recent) -> None:
        mock_recent.return_value = ["Paris, Texas"]

        title, warnings = suggest_film_title()

        self.assertEqual(title, "Paris, Texas")
        self.assertTrue(any("TMDB_API_KEY" in warning for warning in warnings))


if __name__ == "__main__":
    unittest.main()
