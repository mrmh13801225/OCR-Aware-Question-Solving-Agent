"""T3.1 — shared OCR-provider contract suite.

Parametrized over every registered OCR adapter. Each adapter replays its own
fixtures through an injected httpx.MockTransport, so the suite proves every
adapter honors the OCRProvider protocol and maps vendor failures to the same
typed errors — hermetically, no live keys.
"""

from collections.abc import Callable
from pathlib import Path

import httpx
import pytest

from config import OCR_PROVIDER_REGISTRY, Settings
from core.domain.errors import (
    ProviderAuthError,
    ProviderError,
    ProviderRateLimitError,
    ProviderResponseError,
    ProviderTimeoutError,
)

ADAPTER_NAMES = sorted(set(OCR_PROVIDER_REGISTRY) - {"fake"})
IMAGE = b"fake-png-bytes"
FIXTURE_ROOT = Path(__file__).parent / "fixtures"


def _fixture_text(adapter: str) -> str:
    return (FIXTURE_ROOT / adapter / "extract_ok.json").read_text(encoding="utf-8")


def _build(adapter: str, handler: Callable[[httpx.Request], httpx.Response]):
    from providers.ocr.nanonets import NanonetsOCRProvider

    if adapter == "nanonets":
        transport = httpx.Client(transport=httpx.MockTransport(handler))
        provider = NanonetsOCRProvider(api_key="test-key", http_client=transport)
        return provider

    from config import build_ocr_provider

    settings = Settings(_env_file=None, ocr_provider=adapter)  # type: ignore[call-arg]
    return build_ocr_provider(adapter, settings)


@pytest.mark.parametrize("adapter", ADAPTER_NAMES)
class TestOCRContract:
    def test_extract_text_happy_path_returns_text(self, adapter: str) -> None:
        provider = _build(
            adapter, lambda request: httpx.Response(200, content=_fixture_text(adapter).encode())
        )
        extracted = provider.extract_text(IMAGE)
        assert extracted.text.strip()
        assert extracted.provider == adapter

    def test_empty_extraction_handled_gracefully(self, adapter: str) -> None:
        payload = _empty_payload(adapter)
        provider = _build(adapter, lambda request: httpx.Response(200, content=payload.encode()))
        extracted = provider.extract_text(IMAGE)
        assert extracted.text == ""

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
        provider = _build(adapter, lambda request: httpx.Response(status, json={"error": "boom"}))
        with pytest.raises(expected):
            provider.extract_text(IMAGE)

    def test_malformed_json_maps_to_provider_response_error(self, adapter: str) -> None:
        provider = _build(adapter, lambda request: httpx.Response(200, content=b"not-json{"))
        with pytest.raises(ProviderResponseError):
            provider.extract_text(IMAGE)

    def test_timeout_maps_to_provider_timeout_error(self, adapter: str) -> None:
        def timeout_handler(request: httpx.Request) -> httpx.Response:
            raise httpx.ReadTimeout("timed out", request=request)

        provider = _build(adapter, timeout_handler)
        with pytest.raises(ProviderTimeoutError):
            provider.extract_text(IMAGE)


def _empty_payload(adapter: str) -> str:
    path = FIXTURE_ROOT / adapter / "extract_empty.json"
    return path.read_text(encoding="utf-8")
