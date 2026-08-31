"""T3.2 — shared reasoning-provider contract suite.

One suite, parametrized over every registered reasoning adapter. Each adapter
is built against an injected MockTransport replaying its own fixtures, so the
suite proves every adapter honors the ReasoningProvider protocol and maps
vendor failures to the same typed errors — hermetically, no live keys.
"""

import base64
import json
from collections.abc import Callable
from pathlib import Path

import httpx
import pytest

from config import REASONING_PROVIDER_REGISTRY, Settings
from core.domain.errors import (
    ProviderAuthError,
    ProviderError,
    ProviderRateLimitError,
    ProviderResponseError,
    ProviderTimeoutError,
)
from core.domain.models import Option, ParsedBlock

# The 'fake' provider is a deterministic in-process stand-in, not an HTTP
# adapter — the contract suite exercises vendor-shaped adapters only.
ADAPTER_NAMES = sorted(set(REASONING_PROVIDER_REGISTRY) - {"fake"})
OPTIONS = [Option("A", "تهران"), Option("B", "مشهد"), Option("C", "اصفهان"), Option("D", "تبریز")]
BLOCK = ParsedBlock(question_text="کدام شهر پایتخت ایران است؟", options=OPTIONS, raw_text="raw ocr")
IMAGE = b"fake-png-bytes"
FIXTURE_ROOT = Path(__file__).parent / "fixtures"

SOLVE_OK = {
    "content": [{"type": "text", "text": "C"}],
}
CORRECT_OK = {
    "content": [
        {
            "type": "text",
            "text": json.dumps(
                {
                    "question_text": BLOCK.question_text,
                    "options": [{"label": o.label, "text": o.text} for o in OPTIONS],
                },
                ensure_ascii=False,
            ),
        }
    ],
}


def _fixture_path(adapter: str, case: str) -> Path:
    return FIXTURE_ROOT / adapter / f"{case}.json"


def _mock_handler(adapter: str) -> Callable[[httpx.Request], httpx.Response]:
    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content.decode("utf-8"))
        prompt = json.dumps(body, ensure_ascii=False)
        if "minimal" in prompt and "correction" in prompt:
            case = "correct_ok"
        else:
            case = "solve_ok"
        path = _fixture_path(adapter, case)
        if not path.exists():
            return httpx.Response(500, json={"error": f"no fixture {path.name}"})
        return httpx.Response(200, json=json.loads(path.read_text(encoding="utf-8")))

    return handler


def _build(adapter: str, handler: Callable[[httpx.Request], httpx.Response]):
    import anthropic

    from providers.reasoning.claude import ClaudeReasoningProvider
    from providers.reasoning.openai_compatible import OpenAICompatibleReasoningProvider

    transport = httpx.Client(transport=httpx.MockTransport(handler))
    if adapter == "claude":
        client = anthropic.Anthropic(api_key="test-key", http_client=transport)
        return ClaudeReasoningProvider(api_key="test-key", client=client), handler
    if adapter == "openai_compatible":
        provider = OpenAICompatibleReasoningProvider(
            base_url="http://test.local/v1",
            api_key="test-key",
            model="test-model",
            http_client=transport,
        )
        return provider, handler

    from config import build_reasoning_provider

    settings = Settings(_env_file=None, reasoning_provider=adapter)  # type: ignore[call-arg]
    return build_reasoning_provider(adapter, settings), handler


@pytest.mark.parametrize("adapter", ADAPTER_NAMES)
class TestReasoningContract:
    def test_solve_returns_valid_solve_attempt(self, adapter: str) -> None:
        provider, handler = _build(adapter, _mock_handler(adapter))
        attempt = provider.solve(IMAGE, BLOCK.question_text, OPTIONS)
        assert attempt.raw_answer.strip()
        assert attempt.question_text_used == BLOCK.question_text
        assert attempt.attempt_index >= 0

    def test_solve_request_carries_image_question_and_options(self, adapter: str) -> None:
        seen: dict[str, httpx.Request] = {}

        def capturing(request: httpx.Request) -> httpx.Response:
            seen["req"] = request
            path = _fixture_path(adapter, "solve_ok")
            return httpx.Response(200, json=json.loads(path.read_text(encoding="utf-8")))

        provider, _ = _build(adapter, capturing)
        provider.solve(IMAGE, BLOCK.question_text, OPTIONS)
        body = json.loads(seen["req"].content.decode("utf-8"))
        flat = json.dumps(body, ensure_ascii=False)
        assert base64.b64encode(IMAGE).decode() in flat  # image travels in the payload
        assert "کدام شهر" in flat  # question text present
        assert "اصفهان" in flat  # option text present

    def test_correct_returns_valid_parsed_block(self, adapter: str) -> None:
        provider, handler = _build(adapter, _mock_handler(adapter))
        corrected = provider.correct(IMAGE, BLOCK, "Z")
        assert corrected.question_text == BLOCK.question_text
        assert [o.label for o in corrected.options] == ["A", "B", "C", "D"]
        assert [o.text for o in corrected.options] == [o.text for o in OPTIONS]

    def test_correct_request_includes_minimal_edit_constraints(self, adapter: str) -> None:
        seen: dict[str, httpx.Request] = {}

        def capturing(request: httpx.Request) -> httpx.Response:
            seen["req"] = request
            path = _fixture_path(adapter, "correct_ok")
            return httpx.Response(200, json=json.loads(path.read_text(encoding="utf-8")))

        provider, _ = _build(adapter, capturing)
        provider.correct(IMAGE, BLOCK, "Z")
        prompt = json.dumps(json.loads(seen["req"].content.decode("utf-8")), ensure_ascii=False)
        for constraint in ("minimal", "correction", "image"):
            assert constraint in prompt

    @pytest.mark.parametrize(
        ("status", "expected"),
        [
            (401, ProviderAuthError),
            (429, ProviderRateLimitError),
            (500, ProviderResponseError),
        ],
    )
    def test_http_errors_map_to_typed_provider_errors(
        self, adapter: str, status: int, expected: type[ProviderError]
    ) -> None:
        provider, _ = _build(
            adapter, lambda request: httpx.Response(status, json={"error": "boom"})
        )
        with pytest.raises(expected):
            provider.solve(IMAGE, BLOCK.question_text, OPTIONS)

    def test_malformed_json_maps_to_provider_response_error(self, adapter: str) -> None:
        provider, _ = _build(adapter, lambda request: httpx.Response(200, content=b"not-json{"))
        with pytest.raises(ProviderResponseError):
            provider.solve(IMAGE, BLOCK.question_text, OPTIONS)

    def test_timeout_maps_to_provider_timeout_error(self, adapter: str) -> None:
        def timeout_handler(request: httpx.Request) -> httpx.Response:
            raise httpx.ReadTimeout("timed out", request=request)

        provider, _ = _build(adapter, timeout_handler)
        with pytest.raises(ProviderTimeoutError):
            provider.solve(IMAGE, BLOCK.question_text, OPTIONS)
