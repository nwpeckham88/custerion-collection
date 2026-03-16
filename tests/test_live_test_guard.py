from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from custerion_collection.live_test_guard import reserve_live_test_slot


class TestLiveTestGuard(unittest.TestCase):
    def test_reserve_slot_enforces_daily_cap(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            quota_path = Path(tmp) / "quota.json"
            with patch.dict(
                os.environ,
                {
                    "LLM_LIVE_TEST_QUOTA_PATH": str(quota_path),
                    "LLM_LIVE_TEST_MAX_CALLS_PER_DAY": "1",
                    "LLM_LIVE_TEST_COOLDOWN_SECONDS": "0",
                },
                clear=False,
            ):
                first = reserve_live_test_slot(now_ts=100.0)
                second = reserve_live_test_slot(now_ts=101.0)

            self.assertTrue(first.allowed)
            self.assertFalse(second.allowed)
            self.assertIn("budget exhausted", second.reason or "")

    def test_reserve_slot_waits_for_cooldown(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            quota_path = Path(tmp) / "quota.json"
            slept: list[float] = []

            with patch.dict(
                os.environ,
                {
                    "LLM_LIVE_TEST_QUOTA_PATH": str(quota_path),
                    "LLM_LIVE_TEST_MAX_CALLS_PER_DAY": "3",
                    "LLM_LIVE_TEST_COOLDOWN_SECONDS": "10",
                },
                clear=False,
            ):
                reserve_live_test_slot(now_ts=100.0)
                second = reserve_live_test_slot(now_ts=102.0, sleep_fn=lambda seconds: slept.append(seconds))

            self.assertTrue(second.allowed)
            self.assertEqual(len(slept), 1)
            self.assertAlmostEqual(slept[0], 8.0)


if __name__ == "__main__":
    unittest.main()
