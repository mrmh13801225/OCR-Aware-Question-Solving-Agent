"""Datalab OCR adapter: submit-then-poll over datalab.to's marker API.

Contract per datalab.to's published OpenAPI spec (https://www.datalab.to/openapi.json):
POST multipart/form-data to /api/v1/marker with a `file` field and an
X-Api-Key header; the reply carries a request_id; poll GET
/api/v1/marker/{request_id}?poll=true until status == "complete", then read
the top-level `markdown` rendition.

The legacy /api/v1/ocr endpoint is deprecated (response headers: Deprecation,
Sunset 2026-08-31) and serves a degraded pipeline: on math-heavy scans its
per-line text fragments and it carries no markdown field at all. Marker is
the supported endpoint — `mode` governs quality ('balanced' matches the
vendor's own dashboard) and math is recognized automatically.
"""

import json
import logging
import time

import httpx

from core.domain.errors import ProviderResponseError, ProviderTimeoutError
from core.domain.ports import OCRProvider, OCRText
from providers.http import call_vendor, json_field, raise_for_status, trust_env_for
from providers.images import upload_file_tuple

EXTRACT_URL = "https://www.datalab.to/api/v1/marker"
# balanced: the dashboard's default quality tier — math-heavy exam scans need
# it; 'fast' fragments the same content the legacy endpoint did.
MARKER_PARAMS = {"mode": "balanced", "output_format": "markdown"}
TIMEOUT_SECONDS = 120.0
POLL_INTERVAL_SECONDS = 2.0
POLL_LIMIT_SECONDS = 90.0

logger = logging.getLogger(__name__)


class DatalabOCRProvider(OCRProvider):
    """OCRProvider port implementation over datalab.to's marker API.

    The HTTP client is injected so contract tests replay fixtures with no
    network; clock and sleep are injectable so the poll loop runs instantly
    in tests.
    """

    def __init__(
        self,
        api_key: str,
        http_client: httpx.Client | None = None,
        clock=time.monotonic,
        sleep=time.sleep,
    ) -> None:
        self._client = http_client or httpx.Client(
            headers={"X-Api-Key": api_key},
            timeout=TIMEOUT_SECONDS,
            # datalab.to is external: honor system proxy env vars (proxy-gated
            # networks cannot reach foreign hosts directly).
            trust_env=trust_env_for(EXTRACT_URL),
        )
        self._clock = clock
        self._sleep = sleep

    def extract_text(self, image: bytes) -> OCRText:
        request_id = self._submit(image)
        text = self._poll(request_id)
        logger.info("datalab extracted: %s", text)
        return OCRText(text=text, provider="datalab")

    def _submit(self, image: bytes) -> str:
        response = call_vendor(
            "datalab",
            lambda: self._client.post(
                EXTRACT_URL,
                files={"file": upload_file_tuple(image)},
                data=MARKER_PARAMS,
            ),
        )
        raise_for_status(response, "datalab")
        data = json_field(response, "datalab")
        request_id = data.get("request_id")
        if not request_id:
            raise ProviderResponseError("submit reply carried no request_id", provider="datalab")
        return str(request_id)

    def _poll(self, request_id: str) -> str:
        started = self._clock()
        while True:
            response = call_vendor(
                "datalab",
                lambda: self._client.get(f"{EXTRACT_URL}/{request_id}", params={"poll": "true"}),
            )
            raise_for_status(response, "datalab")
            data = json_field(response, "datalab")
            status = data.get("status")
            if status == "complete":
                return _extracted_text(data)
            if data.get("error"):
                raise ProviderResponseError(
                    f"vendor reported failure: {data['error']}", provider="datalab"
                )
            if self._clock() - started > POLL_LIMIT_SECONDS:
                raise ProviderTimeoutError(
                    f"polling exceeded {POLL_LIMIT_SECONDS:.0f}s", provider="datalab"
                )
            self._sleep(POLL_INTERVAL_SECONDS)


def _extracted_text(data: dict) -> str:
    # Marker payload shape (live-verified): the top-level `markdown` field is
    # the complete document rendition; no per-page pages[] on single-image
    # submissions. Empty markdown on a "complete" reply is a vendor failure,
    # not an empty scan — surfacing "" would explode later as a confusing
    # ParseError far from the cause.
    text = str(data.get("markdown") or "").strip()
    if not text:
        raise ProviderResponseError(
            f"vendor reported complete but returned no text: {json.dumps(data)[:300]}",
            provider="datalab",
        )
    return text
