from __future__ import annotations

import os
import unittest
from urllib.error import HTTPError, URLError
from unittest.mock import MagicMock, patch

from custerion_collection.tools import _http_get_json


class TestToolResilience(unittest.TestCase):
    @patch("custerion_collection.tools.time.sleep")
    @patch("custerion_collection.tools.urlopen")
    @patch.dict(os.environ, {"HTTP_RETRY_COUNT": "2", "HTTP_RETRY_BACKOFF_SECONDS": "0"}, clear=False)
    def test_http_get_json_retries_then_succeeds(self, mock_urlopen, _mock_sleep) -> None:
        success_response = MagicMock()
        success_response.read.return_value = b'{"ok": true}'
        success_cm = MagicMock()
        success_cm.__enter__.return_value = success_response
        success_cm.__exit__.return_value = False

        mock_urlopen.side_effect = [
            URLError("temporary network issue"),
            success_cm,
        ]

        payload, error = _http_get_json("https://example.com")

        self.assertIsNone(error)
        self.assertEqual(payload, {"ok": True})
        self.assertEqual(mock_urlopen.call_count, 2)

    @patch("custerion_collection.tools.time.sleep")
    @patch("custerion_collection.tools.urlopen")
    @patch.dict(os.environ, {"HTTP_RETRY_COUNT": "2", "HTTP_RETRY_BACKOFF_SECONDS": "0"}, clear=False)
    def test_http_get_json_does_not_retry_non_retryable_http(self, mock_urlopen, _mock_sleep) -> None:
        mock_urlopen.side_effect = HTTPError(
            url="https://example.com",
            code=404,
            msg="Not Found",
            hdrs=None,
            fp=None,
        )

        payload, error = _http_get_json("https://example.com")

        self.assertIsNone(payload)
        self.assertEqual(error, "HTTP 404")
        self.assertEqual(mock_urlopen.call_count, 1)

    @patch("custerion_collection.tools.time.sleep")
    @patch("custerion_collection.tools.urlopen")
    @patch.dict(
        os.environ,
        {"HTTP_RETRY_COUNT": "not-a-number", "HTTP_RETRY_BACKOFF_SECONDS": "also-bad"},
        clear=False,
    )
    def test_http_get_json_invalid_retry_env_uses_defaults(self, mock_urlopen, _mock_sleep) -> None:
        success_response = MagicMock()
        success_response.read.return_value = b'{}'
        success_cm = MagicMock()
        success_cm.__enter__.return_value = success_response
        success_cm.__exit__.return_value = False
        mock_urlopen.return_value = success_cm

        payload, error = _http_get_json("https://example.com")

        self.assertEqual(payload, {})
        self.assertIsNone(error)


if __name__ == "__main__":
    unittest.main()