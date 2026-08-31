"""OpenAI-compatible reasoning adapter: chat/completions over plain httpx.

Serves any OpenAI-shaped endpoint (vLLM, Ollama, OpenRouter, ...) and is the
client local_vlm reuses; prompts and correction parsing are shared with the
Claude adapter so every reasoning provider demands the same contract.
"""

import base64
import json

import httpx

from core.domain.errors import (
    ProviderAuthError,
    ProviderRateLimitError,
    ProviderResponseError,
    ProviderTimeoutError,
)
from core.domain.models import Option, ParsedBlock, SolveAttempt
from core.domain.ports import ReasoningProvider
from providers.reasoning.prompts import (
    correct_system_prompt,
    correct_user_text,
    solve_system_prompt,
    solve_user_text,
)
from providers.reasoning.replies import parse_correction_reply

MAX_TOKENS = 1024


class OpenAICompatibleReasoningProvider(ReasoningProvider):
    """ReasoningProvider port implementation over POST /chat/completions.

    The HTTP client is injected so contract tests replay fixtures through
    httpx.MockTransport with no network.
    """

    def __init__(
        self,
        base_url: str,
        api_key: str,
        model: str,
        http_client: httpx.Client | None = None,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._model = model
        self._client = http_client or httpx.Client(
            base_url=self._base_url,
            headers={"Authorization": f"Bearer {api_key}"},
            timeout=60.0,
        )

    def solve(self, image: bytes, question_text: str, options: list[Option]) -> SolveAttempt:
        option_lines = "\n".join(f"{o.label}) {o.text}" for o in options)
        content = [
            {"type": "text", "text": solve_user_text(question_text, option_lines)},
            self._image_part(image),
        ]
        reply = self._chat(solve_system_prompt(), content)
        return SolveAttempt(
            raw_answer=reply.strip(), question_text_used=question_text, attempt_index=0
        )

    def correct(self, image: bytes, block: ParsedBlock, failed_answer: str) -> ParsedBlock:
        option_lines = "\n".join(f"{o.label}) {o.text}" for o in block.options)
        content = [
            {
                "type": "text",
                "text": correct_user_text(block.question_text, option_lines, failed_answer),
            },
            self._image_part(image),
        ]
        reply = self._chat(correct_system_prompt(), content)
        return parse_correction_reply(reply, block, provider="openai_compatible")

    def _image_part(self, image: bytes) -> dict:
        return {
            "type": "image_url",
            "image_url": {
                "url": "data:image/png;base64," + base64.b64encode(image).decode("utf-8")
            },
        }

    def _chat(self, system: str, content: list[dict]) -> str:
        try:
            response = self._client.post(
                f"{self._base_url}/chat/completions",
                json={
                    "model": self._model,
                    "max_tokens": MAX_TOKENS,
                    "messages": [
                        {"role": "system", "content": system},
                        {"role": "user", "content": content},
                    ],
                },
            )
        except httpx.TimeoutException as exc:
            raise ProviderTimeoutError(str(exc), provider="openai_compatible") from exc
        except httpx.HTTPError as exc:
            raise ProviderTimeoutError(
                f"connection failed: {exc}", provider="openai_compatible"
            ) from exc
        return _reply_text(response)


def _reply_text(response: httpx.Response) -> str:
    if response.status_code == 401:
        raise ProviderAuthError(response.text, provider="openai_compatible")
    if response.status_code == 429:
        raise ProviderRateLimitError(response.text, provider="openai_compatible")
    if response.status_code >= 400:
        raise ProviderResponseError(response.text, provider="openai_compatible")
    try:
        data = response.json()
        return data["choices"][0]["message"]["content"]
    except (json.JSONDecodeError, KeyError, IndexError, TypeError) as exc:
        raise ProviderResponseError(
            f"malformed reply from vendor: {exc}", provider="openai_compatible"
        ) from exc
