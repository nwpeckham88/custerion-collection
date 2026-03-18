from __future__ import annotations

import unittest
from unittest.mock import patch

from custerion_collection.commentary import build_goal_driven_commentary_plan, parse_srt_to_commentary_segments
from custerion_collection.models import DeepDiveArtifact, DeepDiveSection, FilmIdentity


class TestCommentaryParser(unittest.TestCase):
    def test_parse_srt_to_segments(self) -> None:
        srt = (
            "1\n"
            "00:00:10,500 --> 00:00:12,100\n"
            "<i>Rain on neon.</i>\n\n"
            "2\n"
            "00:00:15,000 --> 00:00:16,000\n"
            "Footsteps echo.\n\n"
        )

        segments = parse_srt_to_commentary_segments(srt)
        self.assertEqual(len(segments), 2)
        self.assertEqual(segments[0].timestamp_ms, 10500)
        self.assertEqual(segments[0].commentary, "Rain on neon.")
        self.assertEqual(segments[1].scene_label, "Subtitle Cue 002")

    def test_parse_srt_ignores_invalid_blocks(self) -> None:
        srt = "garbage\n\n1\nnot a time\ntext\n"
        segments = parse_srt_to_commentary_segments(srt)
        self.assertEqual(segments, [])

    @patch("custerion_collection.commentary._plan_with_llm", return_value=[])
    def test_goal_driven_plan_delays_fact_after_matching_subtitle(self, _mock_llm_plan) -> None:
        srt = (
            "1\n"
            "00:00:30,000 --> 00:00:31,000\n"
            "Deckard enters the spinner garage.\n\n"
            "2\n"
            "00:01:10,000 --> 00:01:11,000\n"
            "Rachael watches from the shadows.\n\n"
        )
        artifact = DeepDiveArtifact(
            film=FilmIdentity(title="Blade Runner", year=1982, canonical_id="local:blade-runner:1982"),
            personalized_intro="A noir meditation on memory and identity.",
            sections=[
                DeepDiveSection(
                    name="Notable Lore",
                    content="Harrison Ford plays Deckard with restrained uncertainty that reshapes the scene dynamics.",
                    confidence=0.8,
                )
            ],
            watch_next=[],
            known_unknowns=[],
            follow_up_media=[],
            citations=[],
        )

        planned = build_goal_driven_commentary_plan(
            subtitle_text=srt,
            artifact=artifact,
            report_markdown="## Notable Lore\nHarrison Ford plays Deckard with restrained uncertainty.",
            max_segments=6,
            spoiler_delay_ms=5000,
            min_gap_ms=5000,
        )

        self.assertGreaterEqual(len(planned), 1)
        self.assertGreaterEqual(planned[0].timestamp_ms or 0, 35000)
        self.assertIn("Deckard", planned[0].commentary)
        self.assertEqual(planned[0].source, "subtitle_goal_planner")


if __name__ == "__main__":
    unittest.main()
