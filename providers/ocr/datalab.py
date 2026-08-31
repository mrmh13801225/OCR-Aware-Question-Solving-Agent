"""Datalab OCR adapter: olm OCR with submit-then-poll over datalab.to."""

import base64
import time

import httpx

from core.domain.errors import ProviderResponseError, ProviderTimeoutError
from core.domain.ports import OCRProvider, OCRText
from providers.http import call_vendor, json_field, raise_for_status

EXTRACT_URL = "https://www.datalab.to/api/v1/olm"
TIMEOUT_SECONDS = 120.0
POLL_INTERVAL_SECONDS = 2.0
POLL_LIMIT_SECONDS = 90.0


class DatalabOCRProvider(OCRProvider):
    """OCRProvider port implementation over the datalab.to olm OCR API.

    The API is asynchronous: submit returns a status_url, polling it until
    success yields the markdown transcription. The HTTP client is injected
    so contract tests replay fixtures with no network; clock and sleep are
    injectable so the poll loop runs instantly in tests.
    """

    def __init__(
        self,
        api_key: str,
        http_client: httpx.Client | None = None,
        clock=time.monotonic,
        sleep=time.sleep,
    ) -> None:
        self._client = http_client or httpx.Client(
            headers={"X-API-Key": api_key},
            timeout=TIMEOUT_SECONDS,
        )
        self._clock = clock
        self._sleep = sleep

    def extract_text(self, image: bytes) -> OCRText:
        status_url = self._submit(image)
        markdown = self._poll(status_url)
        return OCRText(text=markdown, provider="datalab")

    def _submit(self, image: bytes) -> str:
        response = call_vendor(
            "datalab",
            lambda: self._client.post(
                EXTRACT_URL,
                json={
                    "image": base64.b64encode(image).decode("utf-8"),
                    "file_type": "image/png",
                    "model": "olm-base",
                },
            ),
        )
        raise_for_status(response, "datalab")
        data = json_field(response, "datalab")
        try:
            return data["status_url"]
        except KeyError as exc:
            raise ProviderResponseError(
                f"malformed submit reply from vendor: {exc}", provider="datalab"
            ) from exc

    def _poll(self, status_url: str) -> str:
        started = self._clock()
        while True:
            response = call_vendor("datalab", lambda: self._client.get(status_url))
            raise_for_status(response, "datalab")
            data = json_field(response, "datalab")
            if data.get("success"):
                return str(data.get("markdown", ""))
            if data.get("error"):
                raise ProviderResponseError(
                    f"vendor reported failure: {data['error']}", provider="datalab"
                )
            if self._clock() - started > POLL_LIMIT_SECONDS:
                raise ProviderTimeoutError(
                    f"polling exceeded {POLL_LIMIT_SECONDS:.0f}s", provider="datalab"
                )
            self._sleep(POLL_INTERVAL_SECONDS)
