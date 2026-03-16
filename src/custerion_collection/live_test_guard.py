from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

from custerion_collection.config import data_dir


@dataclass(frozen=True)
class LiveTestSlotResult:
    allowed: bool
    reason: str | None = None


def reserve_live_test_slot(
    now_ts: float | None = None,
    sleep_fn: Callable[[float], None] | None = None,
) -> LiveTestSlotResult:
    """Reserve one live LLM test slot with per-day cap and cooldown.

    The quota is persisted to a local JSON file so repeated test runs do not
    unintentionally consume excessive API usage.
    """
    max_calls = _env_int("LLM_LIVE_TEST_MAX_CALLS_PER_DAY", default=3, minimum=1)
    cooldown_seconds = _env_float("LLM_LIVE_TEST_COOLDOWN_SECONDS", default=20.0, minimum=0.0)

    state_path = _quota_path()
    state = _load_state(state_path)

    now = now_ts if now_ts is not None else time.time()
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    if state.get("date") != today:
        state = {"date": today, "count": 0, "last_run_ts": 0.0}

    count = int(state.get("count", 0))
    if count >= max_calls:
        return LiveTestSlotResult(
            allowed=False,
            reason=(
                "Live LLM test budget exhausted for today "
                f"({count}/{max_calls} calls)."
            ),
        )

    last_run_ts = float(state.get("last_run_ts", 0.0))
    wait_seconds = max(0.0, cooldown_seconds - max(0.0, now - last_run_ts))
    if wait_seconds > 0:
        (sleep_fn or time.sleep)(wait_seconds)
        now = now + wait_seconds

    state["count"] = count + 1
    state["last_run_ts"] = now
    _write_state(state_path, state)
    return LiveTestSlotResult(allowed=True)


def _quota_path() -> Path:
    raw = os.getenv("LLM_LIVE_TEST_QUOTA_PATH", "").strip()
    if raw:
        path = Path(raw).expanduser().resolve()
    else:
        path = data_dir() / "diagnostics" / "live_llm_test_quota.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def _load_state(path: Path) -> dict:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}


def _write_state(path: Path, state: dict) -> None:
    path.write_text(json.dumps(state, indent=2, sort_keys=True), encoding="utf-8")


def _env_int(name: str, default: int, minimum: int | None = None, maximum: int | None = None) -> int:
    raw = os.getenv(name)
    if raw is None:
        value = default
    else:
        try:
            value = int(raw.strip())
        except ValueError:
            value = default

    if minimum is not None:
        value = max(minimum, value)
    if maximum is not None:
        value = min(maximum, value)
    return value


def _env_float(name: str, default: float, minimum: float | None = None, maximum: float | None = None) -> float:
    raw = os.getenv(name)
    if raw is None:
        value = default
    else:
        try:
            value = float(raw.strip())
        except ValueError:
            value = default

    if minimum is not None:
        value = max(minimum, value)
    if maximum is not None:
        value = min(maximum, value)
    return value
