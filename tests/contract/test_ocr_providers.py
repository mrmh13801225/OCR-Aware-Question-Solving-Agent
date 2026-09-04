"""T3.1 — shared OCR-provider contract suite.

Parametrized over every registered OCR adapter. Each adapter replays its own
fixtures through an injected httpx.MockTransport, so the suite proves every
adapter honors the OCRProvider protocol and maps vendor failures to the same
typed errors — hermetically, no live keys.
"""

import base64
import logging
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

    settings = Settings(_env_file=None, ocr_provider=adapter)
    return build_ocr_provider(adapter, settings)


@pytest.mark.parametrize("adapter", ADAPTER_NAMES)
class TestOCRContract:
    def test_extract_text_happy_path_returns_text(self, adapter: str) -> None:
        provider = _build(adapter, _fixture_handler(adapter, "extract_ok"))
        extracted = provider.extract_text(IMAGE)
        assert extracted.text.strip()
        assert extracted.provider == adapter

    def test_empty_extraction_handled_gracefully(self, adapter: str) -> None:
        if adapter == "datalab":
            pytest.skip("datalab treats a complete-but-empty reply as a vendor failure")
        provider = _build(adapter, _fixture_handler(adapter, "extract_empty"))
        extracted = provider.extract_text(IMAGE)
        assert extracted.text == ""

    def test_extraction_is_logged_and_carries_no_image(self, adapter: str, caplog) -> None:
        """Every adapter logs the extracted text at INFO, and no log record
        anywhere leaks the image bytes."""
        provider = _build(adapter, _fixture_handler(adapter, "extract_ok"))
        with caplog.at_level(logging.INFO, logger="providers.ocr"):
            provider.extract_text(IMAGE)
        trail = "\n".join(record.getMessage() for record in caplog.records)
        assert f"{adapter} extracted:" in trail  # the choke point every adapter must have
        assert base64.b64encode(IMAGE).decode() not in trail

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


def test_datalab_complete_but_empty_reply_is_a_vendor_error() -> None:
    from providers.ocr.datalab import DatalabOCRProvider

    transport = httpx.Client(
        transport=httpx.MockTransport(_fixture_handler("datalab", "extract_empty"))
    )
    provider = DatalabOCRProvider(
        api_key="test-key", http_client=transport, clock=lambda: 0.0, sleep=lambda _s: None
    )
    with pytest.raises(ProviderResponseError, match="no text"):
        provider.extract_text(IMAGE)


def test_datalab_submit_carries_no_language_lock() -> None:
    """The agent must not be locked to one language: the submit request lets
    the vendor auto-detect instead of hardcoding a `langs` field. The body is
    read inside the handler — that is when the multipart payload is real."""
    bodies: list[bytes] = []
    base_handler = _fixture_handler("datalab", "extract_ok")

    def capturing(request: httpx.Request) -> httpx.Response:
        bodies.append(request.read())
        return base_handler(request)

    provider = _build("datalab", capturing)
    provider.extract_text(IMAGE)
    assert b'name="langs"' not in bodies[0]


def test_datalab_poll_error_field_is_a_vendor_error() -> None:
    from providers.ocr.datalab import DatalabOCRProvider

    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "POST":
            return httpx.Response(
                200, json={"request_id": "req-1", "status": "processing", "success": True}
            )
        return httpx.Response(
            200, json={"request_id": "req-1", "status": "failed", "error": "boom"}
        )

    transport = httpx.Client(transport=httpx.MockTransport(handler))
    provider = DatalabOCRProvider(
        api_key="test-key", http_client=transport, clock=lambda: 0.0, sleep=lambda _s: None
    )
    with pytest.raises(ProviderResponseError, match="vendor reported failure"):
        provider.extract_text(IMAGE)


def test_datalab_poll_timeout_is_a_provider_timeout() -> None:
    from providers.ocr.datalab import DatalabOCRProvider

    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "POST":
            return httpx.Response(
                200, json={"request_id": "req-1", "status": "processing", "success": True}
            )
        return httpx.Response(200, json={"request_id": "req-1", "status": "processing"})

    transport = httpx.Client(transport=httpx.MockTransport(handler))
    clock = iter([0.0, 200.0]).__next__  # started, then past POLL_LIMIT
    provider = DatalabOCRProvider(
        api_key="test-key", http_client=transport, clock=clock, sleep=lambda _s: None
    )
    with pytest.raises(ProviderTimeoutError, match="polling exceeded"):
        provider.extract_text(IMAGE)


def test_local_vlm_extract_prompt_is_language_neutral() -> None:
    from providers.ocr.local_vlm import EXTRACT_SYSTEM

    assert "persian" not in EXTRACT_SYSTEM.lower()


def _fixture_handler(adapter: str, case: str) -> Callable[[httpx.Request], httpx.Response]:
    """Serve fixtures per flow: single-shot adapters get one payload; the
    datalab submit+poll flow gets a POST (submit) payload and a GET (poll)
    payload. Any unexpected method is a contract bug in the adapter.
    """
    if adapter == "datalab":
        submit = (FIXTURE_ROOT / adapter / f"{case}_submit.json").read_bytes()
        poll = (FIXTURE_ROOT / adapter / f"{case}_poll.json").read_bytes()

        def datalab_handler(request: httpx.Request) -> httpx.Response:
            if request.method == "POST":
                return httpx.Response(200, content=submit)
            if request.method == "GET":
                return httpx.Response(200, content=poll)
            return httpx.Response(500, json={"error": f"unexpected method {request.method}"})

        return datalab_handler

    payload = (FIXTURE_ROOT / adapter / f"{case}.json").read_bytes()

    def handler(request: httpx.Request) -> httpx.Response:
        if request.method != "POST":
            return httpx.Response(500, json={"error": f"unexpected method {request.method}"})
        return httpx.Response(200, content=payload)

    return handler
