"""Claude reasoning adapter: solve and image-grounded correction over the Anthropic SDK."""

import base64

import anthropic

from core.domain.errors import (
    ProviderAuthError,
    ProviderError,
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
    transcribe_system_prompt,
    transcribe_user_text,
)
from providers.reasoning.replies import parse_correction_reply

MODEL = "claude-opus-5"
MAX_TOKENS = 1024


class ClaudeReasoningProvider(ReasoningProvider):
    """ReasoningProvider port implementation over the Anthropic Messages API.

    The HTTP client is injected so contract tests can replay fixtures through
    httpx.MockTransport with no network access.
    """

    def __init__(
        self,
        api_key: str,
        model: str = MODEL,
        client: anthropic.Anthropic | None = None,
    ) -> None:
        if client is not None:
            self._client = client
        elif api_key:
            self._client = anthropic.Anthropic(api_key=api_key)
        else:
            # No key and no injected client: let the SDK resolve credentials
            # from the environment (ANTHROPIC_API_KEY / auth profile).
            self._client = anthropic.Anthropic()
        self._model = model

    def solve(self, image: bytes, question_text: str, options: list[Option]) -> SolveAttempt:
        option_lines = "\n".join(f"{o.label}) {o.text}" for o in options)
        text = self._complete(
            solve_system_prompt(), solve_user_text(question_text, option_lines), image
        )
        return SolveAttempt(
            raw_answer=text.strip(),
            question_text_used=question_text,
            attempt_index=0,
        )

    def correct(self, image: bytes, block: ParsedBlock, failed_answer: str) -> ParsedBlock:
        option_lines = "\n".join(f"{o.label}) {o.text}" for o in block.options)
        system = correct_system_prompt()
        user_text = correct_user_text(block.question_text, option_lines, failed_answer)
        payload = self._complete(system, user_text, image)
        try:
            return parse_correction_reply(payload, block, provider="claude")
        except ProviderResponseError:
            payload = self._complete(
                system,
                user_text + "\n\nYour previous reply was not a JSON object. "
                "Respond with ONLY the JSON object, nothing else.",
                image,
            )
            return parse_correction_reply(payload, block, provider="claude")

    def transcribe(self, image: bytes) -> ParsedBlock:
        """Re-read the image from scratch: OCR failed to parse, so the model
        produces a fresh transcription the parser can accept."""
        system = transcribe_system_prompt()
        payload = self._complete(system, transcribe_user_text(), image)
        empty = ParsedBlock(question_text="", options=[], raw_text="")
        try:
            return parse_correction_reply(payload, empty, provider="claude", strict=False)
        except ProviderResponseError:
            payload = self._complete(
                system,
                transcribe_user_text() + "\n\nYour previous reply was not a JSON object. "
                "Respond with ONLY the JSON object, nothing else.",
                image,
            )
            return parse_correction_reply(payload, empty, provider="claude", strict=False)

    def _complete(self, system: str, user_text: str, image: bytes) -> str:
        try:
            response = self._client.messages.create(
                model=self._model,
                max_tokens=MAX_TOKENS,
                system=system,
                messages=[
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "image",
                                "source": {
                                    "type": "base64",
                                    "media_type": "image/png",
                                    "data": base64.standard_b64encode(image).decode("utf-8"),
                                },
                            },
                            {"type": "text", "text": user_text},
                        ],
                    }
                ],
            )
        except anthropic.AnthropicError as exc:
            raise translate_anthropic_error(exc) from exc
        # The SDK's response validation can surface a non-conforming 200 body
        # as a bare error string instead of a Message; treat either as a
        # contract violation.
        if isinstance(response, str):
            raise ProviderResponseError(
                f"malformed reply from vendor: {response}", provider="claude"
            )
        return "".join(b.text for b in response.content if b.type == "text")


def translate_anthropic_error(exc: Exception, provider: str = "claude") -> ProviderError:
    """Map SDK exceptions onto the typed ProviderError hierarchy."""
    if isinstance(exc, anthropic.AuthenticationError):
        return ProviderAuthError(str(exc), provider=provider)
    if isinstance(exc, anthropic.RateLimitError):
        return ProviderRateLimitError(str(exc), provider=provider)
    if isinstance(exc, anthropic.APITimeoutError):
        return ProviderTimeoutError(str(exc), provider=provider)
    if isinstance(exc, anthropic.APIConnectionError):
        return ProviderTimeoutError(f"connection failed: {exc}", provider=provider)
    if isinstance(exc, anthropic.APIStatusError):
        return ProviderResponseError(str(exc), provider=provider)
    return ProviderResponseError(str(exc), provider=provider)
