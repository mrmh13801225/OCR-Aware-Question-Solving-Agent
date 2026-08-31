"""T3.3 — every registered adapter satisfies its runtime-checkable protocol."""

from config import (
    OCR_PROVIDER_REGISTRY,
    REASONING_PROVIDER_REGISTRY,
    FakeOCRProvider,
    FakeReasoningProvider,
)
from core.domain.ports import OCRProvider, ReasoningProvider


def test_ocr_adapters_satisfy_the_protocol() -> None:
    for name in OCR_PROVIDER_REGISTRY:
        provider = _construct_ocr(name)
        assert isinstance(provider, OCRProvider), f"{name} does not satisfy OCRProvider"


def test_reasoning_adapters_satisfy_the_protocol() -> None:
    for name in REASONING_PROVIDER_REGISTRY:
        provider = _construct_reasoning(name)
        assert isinstance(provider, ReasoningProvider), f"{name} does not satisfy ReasoningProvider"


def test_fakes_satisfy_the_protocols_too() -> None:
    assert isinstance(FakeOCRProvider(), OCRProvider)
    assert isinstance(FakeReasoningProvider(), ReasoningProvider)


def _construct_ocr(name: str):
    from providers.ocr.datalab import DatalabOCRProvider
    from providers.ocr.local_vlm import LocalVLMOCRProvider
    from providers.ocr.nanonets import NanonetsOCRProvider

    if name == "nanonets":
        return NanonetsOCRProvider(api_key="k")
    if name == "datalab":
        return DatalabOCRProvider(api_key="k")
    if name == "local_vlm":
        return LocalVLMOCRProvider(base_url="http://x/v1", model="m")
    if name == "fake":
        return FakeOCRProvider()
    raise ValueError(name)


def _construct_reasoning(name: str):
    from providers.reasoning.claude import ClaudeReasoningProvider
    from providers.reasoning.openai_compatible import OpenAICompatibleReasoningProvider

    if name == "claude":
        return ClaudeReasoningProvider(api_key="k")
    if name == "openai_compatible":
        return OpenAICompatibleReasoningProvider(base_url="http://x/v1", api_key="k", model="m")
    if name == "fake":
        return FakeReasoningProvider()
    raise ValueError(name)
