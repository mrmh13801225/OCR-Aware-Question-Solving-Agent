"""Datalab OCR adapter: submit-then-poll over the datalab.to OCR API.

Contract per datalab.to's published OpenAPI spec (https://www.datalab.to/openapi.json):
POST multipart/form-data to /api/v1/ocr with a `file` field and an X-Api-Key
header; the reply carries a request_id; poll GET /api/v1/ocr/{request_id}
?poll=true until status == "complete", then join the per-page text fields.
"""

import json
import logging
import time

import httpx

from core.domain.errors import ProviderResponseError, ProviderTimeoutError
from core.domain.ports import OCRProvider, OCRText
from providers.http import call_vendor, json_field, raise_for_status, trust_env_for
from providers.images import upload_file_tuple

EXTRACT_URL = "https://www.datalab.to/api/v1/ocr"
TIMEOUT_SECONDS = 120.0
POLL_INTERVAL_SECONDS = 2.0
POLL_LIMIT_SECONDS = 90.0

logger = logging.getLogger(__name__)


class DatalabOCRProvider(OCRProvider):
    """OCRProvider port implementation over the datalab.to OCR API.

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
    # Real payload shape (live-verified): pages[].text_lines[].text — the
    # OpenAPI schema types pages as open objects, so the nesting is
    # authoritative from the wire, not the spec. top-level `markdown` kept
    # as a fallback for the documented convenience shape.
    lines: list[str] = []
    for page in data.get("pages") or []:
        for line in page.get("text_lines") or []:
            lines.append(str(line.get("text") or ""))
        if page.get("markdown"):
            lines.append(str(page["markdown"]))
    if not lines:
        lines.append(str(data.get("markdown") or ""))
    text = "\n".join(lines)
    if not text.strip():
        # "complete" with no text is a vendor-side failure, not an empty scan:
        # surfacing it as an empty string would explode later as a confusing
        # ParseError far from the cause.
        raise ProviderResponseError(
            f"vendor reported complete but returned no text: {json.dumps(data)[:300]}",
            provider="datalab",
        )
    return text
