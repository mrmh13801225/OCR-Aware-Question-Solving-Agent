"""Claude reasoning adapter: solve and image-grounded correction over the Anthropic SDK."""

import base64
import json

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

MODEL = "claude-opus-5"
MAX_TOKENS = 1024

_SOLVE_SYSTEM = (
    "You solve Persian multiple-choice questions from a scan image. "
    "The OCR text provided may contain errors; trust the image over the text. "
    "Answer with ONLY the option letter (A, B, C, or D) on its own line."
)

_CORRECT_SYSTEM = (
    "You correct OCR transcription errors in a Persian multiple-choice question, "
    "using the scan image as ground truth. Make the minimal plausible correction: "
    "fix only the characters/words that are wrong, never rewrite the question, "
    "never invent or remove options, never change an option label. "
    "Reply with ONLY a JSON object: "
    '{"question_text": "...", "options": [{"label": "A", "text": "..."}, ...]} '
    "with the same option labels in the same order."
)


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
        user_text = (
            f"OCR text (may be wrong):\n{question_text}\n\nOptions:\n{option_lines}\n\n"
            "Which option is correct? Answer with only the letter."
        )
        text = self._complete(_SOLVE_SYSTEM, user_text, image)
        return SolveAttempt(
            raw_answer=text.strip(),
            question_text_used=question_text,
            attempt_index=0,
        )

    def correct(self, image: bytes, block: ParsedBlock, failed_answer: str) -> ParsedBlock:
        option_lines = "\n".join(f"{o.label}) {o.text}" for o in block.options)
        user_text = (
            f"The OCR text below produced the answer '{failed_answer}', which matches "
            "none of the options — evidence the text is misread. Correct it minimally.\n\n"
            f"OCR text (may be wrong):\n{block.question_text}\n\nOptions:\n{option_lines}"
        )
        payload = self._complete(_CORRECT_SYSTEM, user_text, image)
        return self._parse_correction(payload, block)

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

    def _parse_correction(self, payload: str, original: ParsedBlock) -> ParsedBlock:
        start, end = payload.find("{"), payload.rfind("}")
        if start == -1 or end == -1 or end < start:
            raise ProviderResponseError(
                "correction reply contained no JSON object", provider="claude"
            )
        try:
            data = json.loads(payload[start : end + 1])
            question_text = data["question_text"]
            options = [(o["label"], o["text"]) for o in data["options"]]
        except (json.JSONDecodeError, KeyError, TypeError) as exc:
            raise ProviderResponseError(
                f"correction reply was not a valid block: {exc}", provider="claude"
            ) from exc
        if len(options) != len(original.options):
            raise ProviderResponseError(
                "correction changed the number of options", provider="claude"
            )
        return ParsedBlock(
            question_text=question_text,
            options=[
                Option(label=original.options[i].label, text=text)
                for i, (_label, text) in enumerate(options)
            ],
            raw_text=original.raw_text,
        )


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
