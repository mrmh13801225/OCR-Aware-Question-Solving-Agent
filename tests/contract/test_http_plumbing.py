"""Contract tests for the shared HTTP plumbing added during the live pass."""

import httpx
import pytest

from core.domain.errors import ProviderResponseError
from providers.http import json_field, trust_env_for


def test_json_field_tolerates_sse_done_framing() -> None:
    # GLM gateways append `data: [DONE]` even on non-streaming replies.
    response = httpx.Response(200, content=b'{"id": "1", "choices": []}data: [DONE]\n\n')
    data = json_field(response, "openai_compatible")
    assert data["id"] == "1"


def test_json_field_still_rejects_garbage() -> None:
    response = httpx.Response(200, content=b"not-json{")
    with pytest.raises(ProviderResponseError):
        json_field(response, "openai_compatible")


def test_json_field_rejects_non_object() -> None:
    response = httpx.Response(200, content=b"[1, 2]")
    with pytest.raises(ProviderResponseError):
        json_field(response, "openai_compatible")


def test_trust_env_true_for_external_vendors() -> None:
    assert trust_env_for("https://www.datalab.to/api/v1/ocr") is True
    assert trust_env_for("https://app.nanonets.com/api/v2/OCR/FullText") is True
    assert trust_env_for("https://api.openai.com/v1") is True


def test_trust_env_false_for_local_endpoints() -> None:
    assert trust_env_for("http://localhost:20128/v1") is False
    assert trust_env_for("http://127.0.0.1:8000/v1") is False
    assert trust_env_for("http://localhost:8000/v1") is False


def test_parse_correction_reply_extracts_json_from_prose() -> None:
    """Reasoning models sometimes wrap the JSON in prose or fences; the
    parse takes the first {...} block — verified from string index search."""
    from core.domain.models import Option, ParsedBlock
    from providers.reasoning.replies import parse_correction_reply

    original = ParsedBlock("q", [Option("A", "1"), Option("B", "2")], "raw")
    json_body = (
        '{"question_text": "q2", '
        '"options": [{"label": "A", "text": "1"}, {"label": "B", "text": "2"}]}'
    )
    payload = f"Sure! Here is the correction:\n```json\n{json_body}\n```"
    corrected = parse_correction_reply(payload, original, provider="test")
    assert corrected.question_text == "q2"


def test_call_vendor_retries_once_on_transient_failure() -> None:
    """Live-pass evidence: gateways throw transient DNS/connect errors
    (ENOTFOUND mid-conversation); one retry absorbs them."""
    from providers.http import call_vendor

    calls: list[int] = []

    def flaky() -> httpx.Response:
        calls.append(1)
        if len(calls) == 1:
            raise httpx.ConnectError("ENOTFOUND api.b.ai")
        return httpx.Response(200, json={"ok": True})

    assert call_vendor("test", flaky).status_code == 200
    assert len(calls) == 2


def test_call_vendor_does_not_retry_http_responses() -> None:
    """Non-2xx responses are deterministic vendor answers; only transport
    errors retry. Status classification is raise_for_status's job."""
    from providers.http import call_vendor

    calls: list[int] = []

    def flaky() -> httpx.Response:
        calls.append(1)
        return httpx.Response(401, json={"error": "bad key"})

    response = call_vendor("test", flaky)
    assert response.status_code == 401
    assert len(calls) == 1


def test_local_vlm_sends_bearer_token_when_key_given() -> None:
    """vLLM --api-key and LM Studio gate local models behind a Bearer token;
    Ollama ignores it, so the header is present only when a key is set."""
    from providers.ocr.local_vlm import LocalVLMOCRProvider

    seen: dict[str, httpx.Request] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["req"] = request
        return httpx.Response(200, json={"choices": [{"message": {"content": "text"}}]})

    transport = httpx.Client(transport=httpx.MockTransport(handler))
    provider = LocalVLMOCRProvider(
        base_url="http://test.local/v1", model="m", api_key="secret", http_client=transport
    )
    provider.extract_text(b"img")
    assert seen["req"].headers.get("Authorization") == "Bearer secret"


def test_local_vlm_omits_auth_header_without_key() -> None:
    from providers.ocr.local_vlm import LocalVLMOCRProvider

    seen: dict[str, httpx.Request] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["req"] = request
        return httpx.Response(200, json={"choices": [{"message": {"content": "text"}}]})

    transport = httpx.Client(transport=httpx.MockTransport(handler))
    provider = LocalVLMOCRProvider(
        base_url="http://test.local/v1", model="m", http_client=transport
    )
    provider.extract_text(b"img")
    assert "Authorization" not in seen["req"].headers
