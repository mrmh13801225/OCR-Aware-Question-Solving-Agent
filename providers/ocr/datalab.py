"""Datalab OCR adapter: olm OCR with submit-then-poll over datalab.to."""

import base64
import json
import time

import httpx

from core.domain.errors import (
    ProviderAuthError,
    ProviderRateLimitError,
    ProviderResponseError,
    ProviderTimeoutError,
)
from core.domain.ports import OCRProvider, OCRText

EXTRACT_URL = "https://www.datalab.to/api/v1/olm"
TIMEOUT_SECONDS = 120.0
POLL_INTERVAL_SECONDS = 2.0
POLL_LIMIT_SECONDS = 90.0


class DatalabOCRProvider(OCRProvider):
    """OCRProvider port implementation over the datalab.to olm OCR API.

    The API is asynchronous: submit returns a status_url, polling it until
    success yields the markdown transcription. The HTTP client is injected
    so contract tests replay fixtures with no network.
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
        try:
            status_url = self._submit(image)
            markdown = self._poll(status_url)
        except httpx.TimeoutException as exc:
            raise ProviderTimeoutError(str(exc), provider="datalab") from exc
        except httpx.HTTPError as exc:
            raise ProviderTimeoutError(f"connection failed: {exc}", provider="datalab") from exc
        return OCRText(text=markdown, provider="datalab")

    def _submit(self, image: bytes) -> str:
        response = self._client.post(
            EXTRACT_URL,
            json={
                "image": base64.b64encode(image).decode("utf-8"),
                "file_type": "image/png",
                "model": "olm-base",
            },
        )
        _check_status(response)
        try:
            return response.json()["status_url"]
        except (json.JSONDecodeError, KeyError, TypeError) as exc:
            raise ProviderResponseError(
                f"malformed submit reply from vendor: {exc}", provider="datalab"
            ) from exc

    def _poll(self, status_url: str) -> str:
        started = self._clock()
        while True:
            response = self._client.get(status_url)
            _check_status(response)
            data = _json_body(response)
            if data.get("success"):
                return str(data.get("markdown", ""))
            if "error" in data and data["error"]:
                raise ProviderResponseError(
                    f"vendor reported failure: {data['error']}", provider="datalab"
                )
            if self._clock() - started > POLL_LIMIT_SECONDS:
                raise ProviderTimeoutError(
                    f"polling exceeded {POLL_LIMIT_SECONDS:.0f}s", provider="datalab"
                )
            self._sleep(POLL_INTERVAL_SECONDS)


def _check_status(response: httpx.Response) -> None:
    if response.status_code == 401:
        raise ProviderAuthError(response.text, provider="datalab")
    if response.status_code == 429:
        raise ProviderRateLimitError(response.text, provider="datalab")
    if response.status_code >= 400:
        raise ProviderResponseError(response.text, provider="datalab")


def _json_body(response: httpx.Response) -> dict:
    try:
        data = response.json()
        if not isinstance(data, dict):
            raise TypeError("expected a JSON object")
        return data
    except (json.JSONDecodeError, TypeError) as exc:
        raise ProviderResponseError(
            f"malformed reply from vendor: {exc}", provider="datalab"
        ) from exc
