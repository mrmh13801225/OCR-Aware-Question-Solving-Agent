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
    from providers.ocr.datalab import DatalabOCRProvider
    from providers.ocr.local_vlm import LocalVLMOCRProvider
    from providers.ocr.nanonets import NanonetsOCRProvider

    transport = httpx.Client(transport=httpx.MockTransport(handler))
    if adapter == "nanonets":
        return NanonetsOCRProvider(api_key="test-key", http_client=transport)
    if adapter == "datalab":
        return DatalabOCRProvider(
            api_key="test-key", http_client=transport, clock=lambda: 0.0, sleep=lambda _s: None
        )
    if adapter == "local_vlm":
        return LocalVLMOCRProvider(
            base_url="http://test.local/v1", model="test-vlm", http_client=transport
        )

    from config import build_ocr_provider

    settings = Settings(_env_file=None, ocr_provider=adapter)  # type: ignore[call-arg]
    return build_ocr_provider(adapter, settings)


@pytest.mark.parametrize("adapter", ADAPTER_NAMES)
class TestOCRContract:
    def test_extract_text_happy_path_returns_text(self, adapter: str) -> None:
        provider = _build(adapter, _fixture_handler(adapter, "extract_ok"))
        extracted = provider.extract_text(IMAGE)
        assert extracted.text.strip()
        assert extracted.provider == adapter

    def test_empty_extraction_handled_gracefully(self, adapter: str) -> None:
        provider = _build(adapter, _fixture_handler(adapter, "extract_empty"))
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


def _fixture_handler(adapter: str, case: str) -> Callable[[httpx.Request], httpx.Response]:
    """Serve the fixture for both single-shot (nanonets) and submit+poll (datalab) flows.

    Method-aware: every adapter submits via POST (extract or submit step);
    datalab's poll is the only GET. Any other method is a contract bug in
    the adapter — fail loudly instead of serving the payload.
    """
    payload = (FIXTURE_ROOT / adapter / f"{case}.json").read_bytes()

    def handler(request: httpx.Request) -> httpx.Response:
        if request.method not in ("POST", "GET"):
            return httpx.Response(500, json={"error": f"unexpected method {request.method}"})
        return httpx.Response(200, content=payload)

    return handler
