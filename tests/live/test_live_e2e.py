"""T6 — live E2E against real vendor APIs. Run once with real keys, before submitting:

    pytest -m live -s -v

Reads .env (see .env.example). Tests skip when their provider's key is
absent, so the suite matches whatever you're using. Each test prints
evidence for the WRITEUP: extraction text, solve answers, and the full
deliverable for q113.
"""

import pytest

from config import Settings, build_ocr_provider, build_reasoning_provider
from core.domain.ports import RunEventListener
from core.services.retry_loop import RetryLoop

pytestmark = pytest.mark.live

SAMPLES = "tests/fixtures/samples"


class SilentListener(RunEventListener):
    def on_event(self, event) -> None:
        pass


def _settings() -> Settings:
    return Settings()  # reads .env


def _read(path: str) -> bytes:
    with open(path, "rb") as image:
        return image.read()


def _skip_unless(condition: bool, reason: str) -> None:
    if not condition:
        pytest.skip(reason)


def test_live_nanonets_extracts_q113():
    settings = _settings()
    _skip_unless(settings.nanonets_api_key, "NANONETS_API_KEY not set")
    provider = build_ocr_provider("nanonets", settings)
    extracted = provider.extract_text(_read(f"{SAMPLES}/q113.png"))
    print(f"\n[nanonets] q113: {len(extracted.text)} chars")
    print(extracted.text)
    assert extracted.text.strip(), "nanonets returned empty text for q113"


def test_live_datalab_extracts_q113():
    settings = _settings()
    _skip_unless(settings.datalab_api_key, "DATALAB_API_KEY not set")
    provider = build_ocr_provider("datalab", settings)
    extracted = provider.extract_text(_read(f"{SAMPLES}/q113.png"))
    print(f"\n[datalab] q113: {len(extracted.text)} chars")
    print(extracted.text)
    assert extracted.text.strip(), "datalab returned empty text for q113"


def test_live_openai_compatible_solves():
    settings = _settings()
    _skip_unless(
        settings.openai_compat_base_url and settings.openai_compat_model,
        "OPENAI_COMPAT_BASE_URL/MODEL not set",
    )
    provider = build_reasoning_provider("openai_compatible", settings)
    attempt = provider.solve(_read(f"{SAMPLES}/q113.png"), "کدام گزینه درست است؟", [])
    print(
        f"\n[openai_compatible:{settings.openai_compat_model}] raw answer: {attempt.raw_answer!r}"
    )
    assert attempt.raw_answer.strip()


def test_live_claude_solves():
    settings = _settings()
    _skip_unless(settings.anthropic_api_key, "ANTHROPIC_API_KEY not set")
    provider = build_reasoning_provider("claude", settings)
    attempt = provider.solve(_read(f"{SAMPLES}/q113.png"), "کدام گزینه درست است؟", [])
    print(f"\n[claude] raw answer: {attempt.raw_answer!r}")
    assert attempt.raw_answer.strip()


def test_live_e2e_block_result_q113():
    """The deliverable path with the .env-configured providers and model."""
    settings = _settings()
    ocr = build_ocr_provider(settings.ocr_provider, settings)
    reasoning = build_reasoning_provider(settings.reasoning_provider, settings)
    loop = RetryLoop(
        ocr=ocr, reasoning=reasoning, listener=SilentListener(), retry_cap=settings.retry_cap
    )
    result = loop.solve_block(_read(f"{SAMPLES}/q113.png"))
    print(f"\n[e2e q113] {result.answer} changed={result.changed} attempts={result.attempts}")
    print(result.question_text)
    assert result.answer in {"A", "B", "C", "D"}
    assert result.original_ocr_text.strip()
