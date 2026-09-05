"""T3.2 — shared reasoning-provider contract suite.

One suite, parametrized over every registered reasoning adapter. Each adapter
is built against an injected MockTransport replaying its own fixtures, so the
suite proves every adapter honors the ReasoningProvider protocol and maps
vendor failures to the same typed errors — hermetically, no live keys.
"""

import base64
import json
import logging
from collections.abc import Callable
from pathlib import Path

import httpx
import pytest

from config import REASONING_PROVIDER_REGISTRY
from core.domain.errors import (
    ProviderAuthError,
    ProviderError,
    ProviderRateLimitError,
    ProviderResponseError,
    ProviderTimeoutError,
)
from core.domain.models import Option, ParsedBlock, SolveMode
from core.domain.ports import ReasoningProvider

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
        if "Transcribe this question block" in prompt:
            case = "transcribe_ok"
        elif "minimal" in prompt and "correction" in prompt:
            case = "correct_ok"
        else:
            case = "solve_ok"
        path = _fixture_path(adapter, case)
        if not path.exists():
            return httpx.Response(500, json={"error": f"no fixture {path.name}"})
        return httpx.Response(200, json=json.loads(path.read_text(encoding="utf-8")))

    return handler


def _build(
    adapter: str,
    handler: Callable[[httpx.Request], httpx.Response],
    solve_mode: SolveMode | None = None,
) -> tuple[ReasoningProvider, Callable[[httpx.Request], httpx.Response]]:
    import anthropic

    from providers.reasoning.claude import ClaudeReasoningProvider
    from providers.reasoning.openai_compatible import OpenAICompatibleReasoningProvider

    transport = httpx.Client(transport=httpx.MockTransport(handler))
    if adapter == "claude":
        client = anthropic.Anthropic(api_key="test-key", http_client=transport)
        if solve_mode is None:
            return ClaudeReasoningProvider(api_key="test-key", client=client), handler
        return (
            ClaudeReasoningProvider(api_key="test-key", client=client, solve_mode=solve_mode),
            handler,
        )
    if adapter == "openai_compatible":
        return (
            OpenAICompatibleReasoningProvider(
                base_url="http://test.local/v1",
                api_key="test-key",
                model="test-model",
                http_client=transport,
                solve_mode="image_grounded" if solve_mode is None else solve_mode,
            ),
            handler,
        )
    raise ValueError(adapter)


def _system_text(adapter: str, body: dict) -> str:
    """The system-prompt text from either wire shape (Messages API vs chat)."""
    if adapter == "claude":
        return str(body.get("system") or "")
    return str(body["messages"][0]["content"])


def _reply_with_content(adapter: str, content) -> dict:
    """A vendor reply whose visible content is `content` (either wire shape)."""
    if adapter == "claude":
        return {"content": [{"type": "text", "text": content}]}
    return {
        "choices": [{"index": 0, "message": {"role": "assistant", "content": content}}]
    }


def test_prompts_are_language_neutral() -> None:
    """The agent must not be locked to one language: no prompt names one —
    Persian support lives in the parser/matcher features, not the prompts."""
    from providers.reasoning import prompts

    for text in (
        prompts.solve_system_prompt("image_grounded"),
        prompts.solve_system_prompt("text_only"),
        prompts.correct_system_prompt(),
        prompts.transcribe_system_prompt(),
    ):
        assert "persian" not in text.lower()


@pytest.mark.parametrize("adapter", ADAPTER_NAMES)
class TestReasoningContract:
    def test_solve_returns_valid_solve_attempt(self, adapter: str) -> None:
        provider, handler = _build(adapter, _mock_handler(adapter))
        attempt = provider.solve(IMAGE, BLOCK.question_text, OPTIONS)
        assert attempt.raw_answer.strip()
        assert attempt.question_text_used == BLOCK.question_text
    
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

    def test_transcribe_returns_parseable_block(self, adapter: str) -> None:
        provider, _ = _build(adapter, _mock_handler(adapter))
        transcribed = provider.transcribe(IMAGE)
        assert transcribed.question_text == BLOCK.question_text
        assert [o.label for o in transcribed.options] == ["A", "B", "C", "D"]
        assert transcribed.raw_text  # parseable text, the whole point of the port method

    def test_transcribe_request_carries_image(self, adapter: str) -> None:
        seen: dict[str, httpx.Request] = {}

        def capturing(request: httpx.Request) -> httpx.Response:
            seen["req"] = request
            path = _fixture_path(adapter, "transcribe_ok")
            return httpx.Response(200, json=json.loads(path.read_text(encoding="utf-8")))

        provider, _ = _build(adapter, capturing)
        provider.transcribe(IMAGE)
        flat = json.dumps(json.loads(seen["req"].content.decode("utf-8")), ensure_ascii=False)
        assert base64.b64encode(IMAGE).decode() in flat

    def test_solve_logs_prompt_and_response(self, adapter: str, caplog) -> None:
        provider, _ = _build(adapter, _mock_handler(adapter))
        with caplog.at_level(logging.INFO, logger="providers"):
            provider.solve(IMAGE, BLOCK.question_text, OPTIONS)
        trail = "\n".join(record.getMessage() for record in caplog.records)
        assert BLOCK.question_text in trail  # the prompt's text part
        assert "response:" in trail and "C" in trail  # the response record carries content

    def test_solve_logs_never_carry_the_image(self, adapter: str, caplog) -> None:
        provider, _ = _build(adapter, _mock_handler(adapter))
        with caplog.at_level(logging.INFO, logger="providers"):
            provider.solve(IMAGE, BLOCK.question_text, OPTIONS)
        trail = "\n".join(record.getMessage() for record in caplog.records)
        assert base64.b64encode(IMAGE).decode() not in trail

    @pytest.mark.parametrize("call", ["correct", "transcribe"])
    def test_other_calls_logs_never_carry_the_image(self, adapter: str, call: str, caplog) -> None:
        provider, _ = _build(adapter, _mock_handler(adapter))
        with caplog.at_level(logging.INFO, logger="providers"):
            if call == "correct":
                provider.correct(IMAGE, BLOCK, "Z")
            else:
                provider.transcribe(IMAGE)
        trail = "\n".join(record.getMessage() for record in caplog.records)
        assert base64.b64encode(IMAGE).decode() not in trail

    def test_correct_logs_prompt_and_response(self, adapter: str, caplog) -> None:
        provider, _ = _build(adapter, _mock_handler(adapter))
        with caplog.at_level(logging.INFO, logger="providers"):
            provider.correct(IMAGE, BLOCK, "Z")
        trail = "\n".join(record.getMessage() for record in caplog.records)
        assert BLOCK.question_text in trail  # prompt carries the block
        assert "response:" in trail and "question_text" in trail  # the correction JSON

    @pytest.mark.parametrize("solve_mode", ["image_grounded", "text_only"])
    def test_correct_is_always_image_grounded(self, adapter: str, solve_mode: SolveMode) -> None:
        """The mode's whole point: whatever solve sees, the correction re-reads
        the image — in both modes."""
        seen: dict[str, httpx.Request] = {}

        def capturing(request: httpx.Request) -> httpx.Response:
            seen["req"] = request
            path = _fixture_path(adapter, "correct_ok")
            return httpx.Response(200, json=json.loads(path.read_text(encoding="utf-8")))

        provider, _ = _build(adapter, capturing, solve_mode=solve_mode)
        provider.correct(IMAGE, BLOCK, "Z")
        flat = json.dumps(json.loads(seen["req"].content.decode("utf-8")), ensure_ascii=False)
        assert base64.b64encode(IMAGE).decode() in flat

    def test_text_only_solve_omits_the_image(self, adapter: str) -> None:
        seen: dict[str, httpx.Request] = {}

        def capturing(request: httpx.Request) -> httpx.Response:
            seen["req"] = request
            path = _fixture_path(adapter, "solve_ok")
            return httpx.Response(200, json=json.loads(path.read_text(encoding="utf-8")))

        provider, _ = _build(adapter, capturing, solve_mode="text_only")
        provider.solve(IMAGE, BLOCK.question_text, OPTIONS)
        flat = json.dumps(json.loads(seen["req"].content.decode("utf-8")), ensure_ascii=False)
        assert BLOCK.question_text in flat  # the OCR text still travels
        assert base64.b64encode(IMAGE).decode() not in flat  # but not the pixels

    def test_text_only_solve_does_not_instruct_image_trust(self, adapter: str) -> None:
        """In text_only no image travels, so the system prompt must not tell
        the model to trust one over the text — a false instruction."""
        seen: dict[str, httpx.Request] = {}

        def capturing(request: httpx.Request) -> httpx.Response:
            seen["req"] = request
            path = _fixture_path(adapter, "solve_ok")
            return httpx.Response(200, json=json.loads(path.read_text(encoding="utf-8")))

        provider, _ = _build(adapter, capturing, solve_mode="text_only")
        provider.solve(IMAGE, BLOCK.question_text, OPTIONS)
        body = json.loads(seen["req"].content.decode("utf-8"))
        system_text = _system_text(adapter, body)
        assert "trust the image" not in system_text.lower()
        assert "from a scan image" not in system_text.lower()
        assert "option letter" in system_text.lower()  # the solve contract stays

    def test_image_grounded_solve_keeps_the_image_instruction(self, adapter: str) -> None:
        seen: dict[str, httpx.Request] = {}

        def capturing(request: httpx.Request) -> httpx.Response:
            seen["req"] = request
            path = _fixture_path(adapter, "solve_ok")
            return httpx.Response(200, json=json.loads(path.read_text(encoding="utf-8")))

        provider, _ = _build(adapter, capturing)
        provider.solve(IMAGE, BLOCK.question_text, OPTIONS)
        body = json.loads(seen["req"].content.decode("utf-8"))
        system_text = _system_text(adapter, body)
        assert "image" in system_text.lower()

    def test_default_solve_mode_is_image_grounded(self, adapter: str) -> None:
        seen: dict[str, httpx.Request] = {}

        def capturing(request: httpx.Request) -> httpx.Response:
            seen["req"] = request
            path = _fixture_path(adapter, "solve_ok")
            return httpx.Response(200, json=json.loads(path.read_text(encoding="utf-8")))

        provider, _ = _build(adapter, capturing)
        provider.solve(IMAGE, BLOCK.question_text, OPTIONS)
        flat = json.dumps(json.loads(seen["req"].content.decode("utf-8")), ensure_ascii=False)
        assert base64.b64encode(IMAGE).decode() in flat

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

    def test_null_reply_content_maps_to_provider_response_error(self, adapter: str) -> None:
        """Live-pass regression: reasoning gateways emit `content: null` when
        the model spends its whole token budget thinking — a typed vendor
        failure, never a raw None flowing into reply parsing."""
        null_content = _reply_with_content(adapter, None)
        provider, _ = _build(
            adapter, lambda request: httpx.Response(200, json=null_content)
        )
        with pytest.raises(ProviderResponseError, match="empty reply"):
            provider.solve(IMAGE, BLOCK.question_text, OPTIONS)

    def test_timeout_maps_to_provider_timeout_error(self, adapter: str) -> None:
        def timeout_handler(request: httpx.Request) -> httpx.Response:
            raise httpx.ReadTimeout("timed out", request=request)

        provider, _ = _build(adapter, timeout_handler)
        with pytest.raises(ProviderTimeoutError):
            provider.solve(IMAGE, BLOCK.question_text, OPTIONS)
