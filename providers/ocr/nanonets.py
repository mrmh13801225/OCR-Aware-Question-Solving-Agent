"""Nanonets OCR adapter: full-text extraction over the app.nanonets.com API."""

import json

import httpx

from core.domain.errors import (
    ProviderAuthError,
    ProviderRateLimitError,
    ProviderResponseError,
    ProviderTimeoutError,
)
from core.domain.ports import OCRProvider, OCRText

EXTRACT_URL = "https://app.nanonets.com/api/v2/OCR/FullText"
TIMEOUT_SECONDS = 120.0


class NanonetsOCRProvider(OCRProvider):
    """OCRProvider port implementation over POST /api/v2/OCR/FullText.

    The HTTP client is injected so contract tests replay fixtures through
    httpx.MockTransport with no network.
    """

    def __init__(self, api_key: str, http_client: httpx.Client | None = None) -> None:
        self._client = http_client or httpx.Client(
            auth=(api_key, ""),
            timeout=TIMEOUT_SECONDS,
        )

    def extract_text(self, image: bytes) -> OCRText:
        try:
            response = self._client.post(
                EXTRACT_URL,
                files={"file": ("image.png", image, "image/png")},
            )
        except httpx.TimeoutException as exc:
            raise ProviderTimeoutError(str(exc), provider="nanonets") from exc
        except httpx.HTTPError as exc:
            raise ProviderTimeoutError(f"connection failed: {exc}", provider="nanonets") from exc
        return OCRText(text=_reply_text(response), provider="nanonets")


def _reply_text(response: httpx.Response) -> str:
    if response.status_code == 401:
        raise ProviderAuthError(response.text, provider="nanonets")
    if response.status_code == 429:
        raise ProviderRateLimitError(response.text, provider="nanonets")
    if response.status_code >= 400:
        raise ProviderResponseError(response.text, provider="nanonets")
    return _extracted_text(response)


def _extracted_text(response: httpx.Response) -> str:
    try:
        data = response.json()
        pages = data["result"][0]["page_data"]
        return "\n".join(page.get("raw_text", "") for page in pages)
    except (json.JSONDecodeError, KeyError, IndexError, TypeError) as exc:
        raise ProviderResponseError(
            f"malformed reply from vendor: {exc}", provider="nanonets"
        ) from exc
