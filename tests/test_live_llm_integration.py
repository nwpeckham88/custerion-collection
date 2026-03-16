from __future__ import annotations

import os
import unittest

from custerion_collection.config import model_name
from custerion_collection.live_test_guard import reserve_live_test_slot


class TestLiveLLMIntegration(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        if os.getenv("RUN_LLM_LIVE_TESTS", "0").strip() != "1":
            raise unittest.SkipTest("RUN_LLM_LIVE_TESTS is not enabled")

        if not os.getenv("OPENAI_API_KEY", "").strip():
            raise unittest.SkipTest("OPENAI_API_KEY is not configured")

        base_url = os.getenv("OPENAI_BASE_URL", "").strip()
        if base_url and not base_url.startswith(("http://", "https://")):
            raise unittest.SkipTest(
                "OPENAI_BASE_URL must include protocol, for example "
                "https://openrouter.ai/api/v1"
            )

        # Prevent interactive trace prompts during test runs.
        os.environ.setdefault("CREWAI_TRACING_ENABLED", "false")

    def test_live_llm_smoke(self) -> None:
        # Import lazily to keep local unit runs fast and isolated when live tests are disabled.
        from crewai import Agent, Crew, LLM, Process, Task

        live_model = os.getenv("LLM_LIVE_TEST_MODEL", "").strip() or model_name(role="Script Editor")
        normalized_model = _normalize_live_model_for_openrouter(live_model)

        try:
            llm = LLM(model=normalized_model)
        except ImportError as exc:
            raise unittest.SkipTest(
                "Live LLM test setup is incompatible with current CrewAI provider support: "
                f"{exc}. Try setting LLM_LIVE_TEST_MODEL=openai/<model> when using OPENAI_BASE_URL."
            )

        reservation = reserve_live_test_slot()
        if not reservation.allowed:
            raise unittest.SkipTest(reservation.reason or "live test quota guard rejected execution")

        agent = Agent(
            role="Live Test Agent",
            goal="Return a fixed sentinel string to verify provider connectivity.",
            backstory="A deterministic smoke-test assistant.",
            llm=llm,
            verbose=False,
        )

        task = Task(
            description="Reply with exactly LIVE_TEST_OK and no other text.",
            expected_output="LIVE_TEST_OK",
            agent=agent,
        )

        crew = Crew(
            agents=[agent],
            tasks=[task],
            process=Process.sequential,
            verbose=False,
        )

        try:
            result = str(crew.kickoff()).upper()
        except Exception as exc:
            text = str(exc)
            if "Connection error" in text or "UnsupportedProtocol" in text:
                raise unittest.SkipTest(
                    "Live LLM test skipped due to connection/provider setup issue: "
                    f"{text}"
                )
            raise
        self.assertIn("LIVE_TEST_OK", result)


def _normalize_live_model_for_openrouter(model: str) -> str:
    """Use OpenAI provider routing for OpenRouter-compatible endpoints.

    CrewAI requires a recognized provider prefix unless LiteLLM is installed.
    """
    known_prefixes = (
        "openai/",
        "anthropic/",
        "claude/",
        "azure/",
        "azure_openai/",
        "google/",
        "gemini/",
        "bedrock/",
        "aws/",
    )
    if model.startswith(known_prefixes):
        return model

    base_url = os.getenv("OPENAI_BASE_URL", "").strip().lower()
    if "openrouter.ai" in base_url:
        return f"openai/{model}"
    return model


if __name__ == "__main__":
    unittest.main()
