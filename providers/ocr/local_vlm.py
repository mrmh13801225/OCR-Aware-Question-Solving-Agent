"""Local-VLM OCR adapter: transcription via an OpenAI-compatible vision endpoint."""

import base64

import httpx

from core.domain.errors import ProviderResponseError
from core.domain.ports import OCRProvider, OCRText
from providers.http import call_vendor, json_field, raise_for_status

EXTRACT_SYSTEM = (
    "You transcribe Persian exam scans verbatim. Output ONLY the text visible "
    "in the image: the question and its numbered options, one per line, "
    "exactly as printed. No commentary, no translation, no markdown."
)
MAX_TOKENS = 2048


class LocalVLMOCRProvider(OCRProvider):
    """OCRProvider port implementation over a local vLLM/Ollama endpoint.

    Reuses the OpenAI chat/completions wire shape (the same family the
    openai_compatible reasoning adapter speaks) pointed at a locally served
    vision model. The HTTP client is injected so contract tests replay
    fixtures through httpx.MockTransport with no network or local model.
    """

    def __init__(
        self,
        base_url: str,
        model: str,
        http_client: httpx.Client | None = None,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._model = model
        self._client = http_client or httpx.Client(timeout=120.0)

    def extract_text(self, image: bytes) -> OCRText:
        response = call_vendor(
            "local_vlm",
            lambda: self._client.post(
                f"{self._base_url}/chat/completions",
                json={
                    "model": self._model,
                    "max_tokens": MAX_TOKENS,
                    "messages": [
                        {"role": "system", "content": EXTRACT_SYSTEM},
                        {
                            "role": "user",
                            "content": [
                                {
                                    "type": "image_url",
                                    "image_url": {
                                        "url": "data:image/png;base64,"
                                        + base64.b64encode(image).decode("utf-8")
                                    },
                                },
                                {"type": "text", "text": "Transcribe this scan."},
                            ],
                        },
                    ],
                },
            ),
        )
        raise_for_status(response, "local_vlm")
        data = json_field(response, "local_vlm")
        try:
            text = data["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as exc:
            raise ProviderResponseError(
                f"malformed reply from vendor: {exc}", provider="local_vlm"
            ) from exc
        return OCRText(text=text, provider="local_vlm")
