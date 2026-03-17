from __future__ import annotations

import unittest
import tempfile
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

from custerion_collection.api import _RUNS, _RUNS_LOCK, app
from custerion_collection.service import DeepDiveRunResult


class TestApi(unittest.TestCase):
    def setUp(self) -> None:
        with _RUNS_LOCK:
            _RUNS.clear()
        self.client = TestClient(app)

    @patch("custerion_collection.api.execute_deep_dive")
    def test_deep_dive_success(self, mock_execute_deep_dive) -> None:
        mock_execute_deep_dive.return_value = DeepDiveRunResult(
            title="The Red Shoes",
            markdown="## Personalized Intro\nA long-form result with evidence https://example.com",
            status="success",
            warnings=[],
            diagnostics_path="/tmp/diag.json",
            markdown_path="/tmp/out.md",
            artifact_json_path="/tmp/out.json",
            html_path="/tmp/out.html",
        )

        response = self.client.post(
            "/deep-dive",
            json={"title": "The Red Shoes", "suggest": False, "process_mode": "hierarchical", "dry_run": False},
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["title"], "The Red Shoes")
        self.assertEqual(payload["status"], "success")

    @patch("custerion_collection.api.execute_deep_dive")
    def test_deep_dive_value_error_returns_400(self, mock_execute_deep_dive) -> None:
        mock_execute_deep_dive.side_effect = ValueError("quality gate failed")

        response = self.client.post(
            "/deep-dive",
            json={"title": "The Red Shoes", "suggest": False, "process_mode": "hierarchical", "dry_run": False},
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn("quality gate failed", response.json()["detail"])

    def test_health(self) -> None:
        response = self.client.get("/health")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["status"], "ok")

    @patch("custerion_collection.api.list_recent_artifacts")
    def test_artifacts_list(self, mock_list_recent_artifacts) -> None:
        mock_list_recent_artifacts.return_value = [
            {
                "title": "The Red Shoes",
                "slug": "the-red-shoes-20260317-100000",
                "markdown_path": "/tmp/out.md",
                "artifact_json_path": "/tmp/out.json",
                "html_path": "/tmp/out.html",
                "updated_at": "2026-03-17T10:00:00+00:00",
            }
        ]

        response = self.client.get("/artifacts")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.json()), 1)
        self.assertEqual(response.json()[0]["title"], "The Red Shoes")

    @patch("custerion_collection.api._run_deep_dive_background")
    def test_deep_dive_start_queues_run(self, _mock_runner) -> None:
        response = self.client.post(
            "/deep-dive/start",
            json={"title": "The Red Shoes", "suggest": False, "process_mode": "hierarchical", "dry_run": False},
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertIn("run_id", payload)
        self.assertEqual(payload["status"], "queued")

    def test_deep_dive_status_missing_run(self) -> None:
        response = self.client.get("/deep-dive/not-found")

        self.assertEqual(response.status_code, 404)

    def test_deep_dive_status_includes_events(self) -> None:
        with _RUNS_LOCK:
            _RUNS["run-1"] = {
                "run_id": "run-1",
                "status": "running",
                "stage": "Running",
                "progress": 42,
                "started_at": "2026-03-17T00:00:00+00:00",
                "updated_at": "2026-03-17T00:00:01+00:00",
                "events": ["System: Run queued", "Agent: researching"],
                "result": None,
                "error": None,
            }

        response = self.client.get("/deep-dive/run-1")

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["events"], ["System: Run queued", "Agent: researching"])

    def test_regenerate_html_missing_markdown_returns_404(self) -> None:
        response = self.client.post("/artifacts/blade-runner-20260317-190129/html/regenerate")

        self.assertEqual(response.status_code, 404)

    @patch("custerion_collection.api.upsert_html_artifact_for_slug")
    @patch("custerion_collection.api.render_html_report_with_retry")
    @patch("custerion_collection.api.artifact_title_for_slug")
    @patch("custerion_collection.api.latest_markdown_artifact_for_slug")
    def test_regenerate_html_success(
        self,
        mock_latest_markdown,
        mock_title,
        mock_render,
        mock_upsert,
    ) -> None:
        markdown_path = Path("/tmp/blade-runner-20260317-190129.md")
        with patch.object(Path, "exists", return_value=True), patch.object(
            Path, "read_text", return_value="## Personalized Intro\nLong-form markdown"
        ):
            mock_latest_markdown.return_value = markdown_path
            mock_title.return_value = "Blade Runner"
            mock_render.return_value = ("<!doctype html><html><body>ok</body></html>", None)
            mock_upsert.return_value = Path("/tmp/blade-runner-20260317-190129.html")

            response = self.client.post("/artifacts/blade-runner-20260317-190129/html/regenerate")

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["slug"], "blade-runner-20260317-190129")
        self.assertEqual(payload["html_path"], "/tmp/blade-runner-20260317-190129.html")

    @patch("custerion_collection.api.list_tts_voices_for_slug")
    def test_tts_voices_success(self, mock_voices) -> None:
        mock_voices.return_value = ("p225", ["p225", "p226"])

        response = self.client.get("/artifacts/blade-runner-20260317-190129/tts/voices")

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["default_voice"], "p225")
        self.assertEqual(payload["voices"], ["p225", "p226"])

    @patch("custerion_collection.api.list_tts_voices_for_slug")
    def test_tts_voices_unavailable_returns_503(self, mock_voices) -> None:
        mock_voices.side_effect = RuntimeError("Local TTS runtime is unavailable")

        response = self.client.get("/artifacts/blade-runner-20260317-190129/tts/voices")

        self.assertEqual(response.status_code, 503)

    @patch("custerion_collection.api.synthesize_tts_audio_for_slug")
    def test_tts_audio_success(self, mock_synthesize) -> None:
        with tempfile.NamedTemporaryFile(suffix=".wav") as tmp:
            tmp.write(b"RIFF....WAVE")
            tmp.flush()
            mock_synthesize.return_value = Path(tmp.name)

            response = self.client.get("/artifacts/blade-runner-20260317-190129/tts/audio")

            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.headers.get("content-type"), "audio/wav")
            mock_synthesize.assert_called_with(
                slug="blade-runner-20260317-190129",
                voice=None,
                mode="full",
            )

    @patch("custerion_collection.api.latest_html_artifact_for_slug")
    def test_artifact_html_sanitizes_placeholder_links(self, mock_latest_html) -> None:
        with tempfile.NamedTemporaryFile(suffix=".html", mode="w+", encoding="utf-8") as tmp:
            tmp.write("<html><body><a href='https://example.com/fake'>source</a></body></html>")
            tmp.flush()
            mock_latest_html.return_value = Path(tmp.name)

            response = self.client.get("/artifacts/blade-runner/html")

            self.assertEqual(response.status_code, 200)
            self.assertNotIn("example.com", response.text)


if __name__ == "__main__":
    unittest.main()
