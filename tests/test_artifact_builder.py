from __future__ import annotations

import unittest

from custerion_collection.artifact_builder import build_deep_dive_artifact


class TestArtifactBuilder(unittest.TestCase):
    def test_build_artifact_parses_sections_and_bounds_media(self) -> None:
        markdown = """
## Personalized Intro
Why this film now for you.

## History
Grounded in post-war ballet culture.

## Craft
Cinematography emphasizes expressive color.

## Industry
Successful release and long-tail acclaim.

## Notable Lore
Famously influenced later directors.

## What To Watch Next
- Black Narcissus
- The Tales of Hoffmann

## Known Unknowns
- Box-office split by region is uncertain.

## Follow-Up Media
1. Wikipedia article: https://en.wikipedia.org/wiki/The_Red_Shoes_(film)
2. Video essay: https://www.youtube.com/watch?v=abc123
3. Related film: https://www.themoviedb.org/movie/1
""".strip()

        artifact = build_deep_dive_artifact("The Red Shoes (1948)", markdown)

        self.assertEqual(artifact.film.title, "The Red Shoes")
        self.assertEqual(artifact.film.year, 1948)
        self.assertEqual([section.name for section in artifact.sections], ["History", "Craft", "Industry", "Notable Lore"])
        self.assertGreaterEqual(len(artifact.watch_next), 2)
        self.assertGreaterEqual(len(artifact.known_unknowns), 1)
        self.assertEqual(len(artifact.follow_up_media), 3)
        self.assertLessEqual(len(artifact.follow_up_media), 8)
        self.assertGreaterEqual(len(artifact.citations), 3)


if __name__ == "__main__":
    unittest.main()