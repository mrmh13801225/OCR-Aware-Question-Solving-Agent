"""T6 — live E2E against real vendor APIs. Run once with real keys, before submitting:

    pytest -m live

Requires a .env with the provider keys (see .env.example). Each test prints
evidence for the WRITEUP: extraction lengths, solve answers, and the full
deliverable JSON for q113.
"""

import pytest

from config import Settings, build_ocr_provider, build_reasoning_provider
from core.domain.ports import RunEventListener
from core.services.retry_loop import RetryLoop

pytestmark = pytest.mark.live

SAMPLES = "tests/fixtures/samples"


class _SilentListener(RunEventListener):
    def on_event(self, event) -> None:
        pass


def _settings() -> Settings:
    return Settings()  # reads .env


def _read(path: str) -> bytes:
    with open(path, "rb") as image:
        return image.read()


def test_live_nanonets_extracts_q113():
    settings = _settings()
    provider = build_ocr_provider("nanonets", settings)
    extracted = provider.extract_text(_read(f"{SAMPLES}/q113.png"))
    print(f"\n[nanonets] q113: {len(extracted.text)} chars")
    print(extracted.text)
    assert extracted.provider == "nanonets"
    assert extracted.text.strip(), "nanonets returned empty text for q113"


def test_live_datalab_extracts_q113():
    settings = _settings()
    provider = build_ocr_provider("datalab", settings)
    extracted = provider.extract_text(_read(f"{SAMPLES}/q113.png"))
    print(f"\n[datalab] q113: {len(extracted.text)} chars")
    print(extracted.text)
    assert extracted.provider == "datalab"
    assert extracted.text.strip(), "datalab returned empty text for q113"


def test_live_claude_solves():
    settings = _settings()
    provider = build_reasoning_provider("claude", settings)
    attempt = provider.solve(
        _read(f"{SAMPLES}/q113.png"),
        "کدام گزینه درست است؟",
        [],
    )
    print(f"\n[claude] raw answer: {attempt.raw_answer!r}")
    assert attempt.raw_answer.strip()


def test_live_e2e_block_result_q113():
    """The full deliverable path: OCR (configured provider) -> loop -> BlockResult."""
    settings = _settings()
    ocr = build_ocr_provider(settings.ocr_provider, settings)
    reasoning = build_reasoning_provider(settings.reasoning_provider, settings)
    loop = RetryLoop(
        ocr=ocr, reasoning=reasoning, listener=_SilentListener(), retry_cap=settings.retry_cap
    )
    result = loop.solve_block(_read(f"{SAMPLES}/q113.png"))
    print(f"\n[e2e q113] {result.answer} changed={result.changed} attempts={result.attempts}")
    print(result.question_text)
    assert result.answer in {"A", "B", "C", "D"}
    assert result.original_ocr_text.strip()
