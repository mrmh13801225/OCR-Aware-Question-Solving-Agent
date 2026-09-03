"""Nanonets OCR adapter: full-text extraction over the app.nanonets.com API."""

import httpx

from core.domain.errors import ProviderResponseError
from core.domain.ports import OCRProvider, OCRText
from providers.http import call_vendor, json_field, raise_for_status, trust_env_for

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
            trust_env=trust_env_for(EXTRACT_URL),  # external: honor system proxy
        )

    def extract_text(self, image: bytes) -> OCRText:
        response = call_vendor(
            "nanonets",
            lambda: self._client.post(
                EXTRACT_URL,
                files={"file": ("image.png", image, "image/png")},
            ),
        )
        raise_for_status(response, "nanonets")
        return OCRText(text=_extracted_text(response), provider="nanonets")


def _extracted_text(response: httpx.Response) -> str:
    data = json_field(response, "nanonets")
    try:
        pages = data["result"][0]["page_data"]
        return "\n".join(page.get("raw_text", "") for page in pages)
    except (KeyError, IndexError, TypeError) as exc:
        raise ProviderResponseError(
            f"malformed reply from vendor: {exc}", provider="nanonets"
        ) from exc
