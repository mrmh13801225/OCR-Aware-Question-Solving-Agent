"""OpenAI-compatible reasoning adapter: chat/completions over plain httpx.

Serves any OpenAI-shaped endpoint (vLLM, Ollama, OpenRouter, ...) and is the
client local_vlm reuses; prompts and correction parsing are shared with the
Claude adapter so every reasoning provider demands the same contract.
"""

import base64

import httpx

from core.domain.errors import ProviderResponseError
from core.domain.models import Option, ParsedBlock, SolveAttempt
from core.domain.ports import ReasoningProvider
from providers.http import call_vendor, json_field, raise_for_status, trust_env_for
from providers.reasoning.prompts import (
    correct_system_prompt,
    correct_user_text,
    solve_system_prompt,
    solve_user_text,
    transcribe_system_prompt,
    transcribe_user_text,
)
from providers.reasoning.replies import parse_correction_reply

# Reasoning models (GLM, DeepSeek-R1 class) spend hundreds of tokens in
# reasoning_content before emitting content; a tight budget starves the
# visible answer to empty. 4096 leaves room for reasoning plus the reply.
MAX_TOKENS = 4096


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
            timeout=600.0,  # measured: reasoning models on image+correction can take ~7 minutes
            # local gateways must bypass the proxy; external vendors need it
            trust_env=trust_env_for(self._base_url),
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
        return self._block_from_chat(
            correct_system_prompt(), content, block, provider="openai_compatible"
        )

    def transcribe(self, image: bytes) -> ParsedBlock:
        """Re-read the image from scratch: OCR failed to parse, so the model
        produces a fresh transcription the parser can accept."""
        content = [
            {"type": "text", "text": transcribe_user_text()},
            self._image_part(image),
        ]
        empty = ParsedBlock(question_text="", options=[], raw_text="")
        return self._block_from_chat(
            transcribe_system_prompt(), content, empty, provider="openai_compatible", strict=False
        )

    def _block_from_chat(
        self,
        system: str,
        content: list[dict],
        original: ParsedBlock,
        provider: str,
        strict: bool = True,
    ) -> ParsedBlock:
        """Chat → JSON block, with one re-ask when the model replies without
        JSON (reasoning models occasionally answer conversationally)."""
        reply = self._chat(system, content)
        try:
            return parse_correction_reply(reply, original, provider=provider, strict=strict)
        except ProviderResponseError:
            nudge = dict(content[0])
            nudge["text"] = (
                f"{content[0]['text']}\n\nYour previous reply was not a JSON object. "
                "Respond with ONLY the JSON object, nothing else."
            )
            reply = self._chat(system, [nudge, *content[1:]])
            return parse_correction_reply(reply, original, provider=provider, strict=strict)

    def _image_part(self, image: bytes) -> dict:
        return {
            "type": "image_url",
            "image_url": {
                "url": "data:image/png;base64," + base64.b64encode(image).decode("utf-8")
            },
        }

    def _chat(self, system: str, content: list[dict]) -> str:
        response = call_vendor(
            "openai_compatible",
            lambda: self._client.post(
                f"{self._base_url}/chat/completions",
                json={
                    "model": self._model,
                    "max_tokens": MAX_TOKENS,
                    "messages": [
                        {"role": "system", "content": system},
                        {"role": "user", "content": content},
                    ],
                },
            ),
        )
        raise_for_status(response, "openai_compatible")
        data = json_field(response, "openai_compatible")
        try:
            return data["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as exc:
            raise ProviderResponseError(
                f"malformed reply from vendor: {exc}", provider="openai_compatible"
            ) from exc
