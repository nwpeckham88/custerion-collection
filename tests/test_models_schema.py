from __future__ import annotations

import unittest
from datetime import datetime, timezone

from pydantic import ValidationError

from custerion_collection.models import DeepDiveArtifact, DeepDiveSection, FilmIdentity, FollowUpMediaItem
from custerion_collection.models import deep_dive_artifact_json_schema


class TestModelSchema(unittest.TestCase):
    def test_deep_dive_schema_contains_expected_fields(self) -> None:
        schema = deep_dive_artifact_json_schema()
        props = schema.get("properties", {})

        self.assertIn("film", props)
        self.assertIn("sections", props)
        self.assertIn("follow_up_media", props)
        self.assertIn("citations", props)

    def test_follow_up_media_duplicate_url_rejected(self) -> None:
        item1 = FollowUpMediaItem(
            kind="article",
            title="A",
            url="https://example.com/a",
            rationale="x",
            relevance_score=0.6,
            source_confidence=0.7,
        )
        item2 = FollowUpMediaItem(
            kind="article",
            title="B",
            url="https://example.com/a",
            rationale="y",
            relevance_score=0.6,
            source_confidence=0.7,
        )

        with self.assertRaises(ValidationError):
            DeepDiveArtifact(
                film=FilmIdentity(title="Film", year=2020, canonical_id="local:film:2020"),
                personalized_intro="intro",
                sections=[DeepDiveSection(name="History", content="x", confidence=0.8)],
                watch_next=[],
                known_unknowns=[],
                follow_up_media=[item1, item2],
                citations=[],
                created_at=datetime.now(timezone.utc),
            )


if __name__ == "__main__":
    unittest.main()
