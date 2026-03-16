from __future__ import annotations

import os
import unittest
from unittest.mock import patch

from custerion_collection.tools import (
    fetch_cultural_context,
    fetch_follow_up_media,
    fetch_history_context,
    fetch_industry_context,
    fetch_technical_context,
)


class TestTools(unittest.TestCase):
    def test_missing_configs_still_include_title(self) -> None:
        title = "The Red Shoes"
        outputs = [
            fetch_history_context(title),
            fetch_technical_context(title),
            fetch_industry_context(title),
        ]

        for output in outputs:
            self.assertIn(title, output)

    @patch.dict(os.environ, {}, clear=True)
    def test_history_context_requires_jellyfin_env(self) -> None:
        output = fetch_history_context("The Red Shoes")
        self.assertIn("Jellyfin adapter is not configured", output)

    @patch("custerion_collection.tools._http_get_json")
    def test_cultural_context_from_wikipedia(self, mock_get_json) -> None:
        mock_get_json.side_effect = [
            (
                {
                    "query": {
                        "search": [
                            {
                                "title": "The Red Shoes (film)",
                                "snippet": "A <b>British</b> drama film",
                            }
                        ]
                    }
                },
                None,
            ),
            (
                {
                    "extract": "Released in 1948 and acclaimed for visual style.",
                    "content_urls": {
                        "desktop": {
                            "page": "https://en.wikipedia.org/wiki/The_Red_Shoes_(film)"
                        }
                    },
                },
                None,
            ),
        ]

        output = fetch_cultural_context("The Red Shoes")

        self.assertIn("Wikipedia match", output)
        self.assertIn("British drama film", output)
        self.assertIn("Released in 1948", output)

    @patch("custerion_collection.tools._tmdb_movie_details")
    @patch("custerion_collection.tools._tmdb_resolve_movie")
    def test_technical_context_from_tmdb(self, mock_resolve, mock_details) -> None:
        mock_resolve.return_value = ({"id": 42}, None)
        mock_details.return_value = (
            {
                "title": "The Red Shoes",
                "release_date": "1948-09-06",
                "runtime": 133,
                "genres": [{"name": "Drama"}],
                "credits": {
                    "crew": [{"job": "Director", "name": "Michael Powell"}],
                    "cast": [{"name": "Moira Shearer"}, {"name": "Anton Walbrook"}],
                },
            },
            None,
        )

        output = fetch_technical_context("The Red Shoes")

        self.assertIn("Michael Powell", output)
        self.assertIn("133 minutes", output)
        self.assertIn("Moira Shearer", output)

    @patch.dict(os.environ, {"YOUTUBE_API_KEY": "token"}, clear=True)
    @patch("custerion_collection.tools._tmdb_movie_details")
    @patch("custerion_collection.tools._tmdb_resolve_movie")
    @patch("custerion_collection.tools._http_get_json")
    def test_follow_up_media_is_bounded(self, mock_get_json, mock_resolve, mock_details) -> None:
        mock_get_json.side_effect = [
            (
                {
                    "query": {
                        "search": [{"title": "The Red Shoes (film)"}],
                    }
                },
                None,
            ),
            (
                {
                    "items": [
                        {"id": {"videoId": "a1"}, "snippet": {"title": "Interview 1"}},
                        {"id": {"videoId": "a2"}, "snippet": {"title": "Interview 2"}},
                        {"id": {"videoId": "a3"}, "snippet": {"title": "Interview 3"}},
                    ]
                },
                None,
            ),
        ]
        mock_resolve.return_value = ({"id": 42}, None)
        mock_details.return_value = (
            {
                "recommendations": {
                    "results": [
                        {"id": 1, "title": "Black Narcissus"},
                        {"id": 2, "title": "The Tales of Hoffmann"},
                        {"id": 3, "title": "A Matter of Life and Death"},
                    ]
                }
            },
            None,
        )

        output = fetch_follow_up_media("The Red Shoes")

        self.assertIn("bounded to", output)
        self.assertIn("Wikipedia article", output)
        self.assertIn("Related film", output)
        self.assertIn("YouTube", output)


if __name__ == "__main__":
    unittest.main()
