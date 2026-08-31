"""Shared reply parsing: correction JSON -> ParsedBlock, for every adapter."""

import json

from core.domain.errors import ProviderResponseError
from core.domain.models import Option, ParsedBlock


def parse_correction_reply(payload: str, original: ParsedBlock, provider: str) -> ParsedBlock:
    start, end = payload.find("{"), payload.rfind("}")
    if start == -1 or end == -1 or end < start:
        raise ProviderResponseError("correction reply contained no JSON object", provider=provider)
    try:
        data = json.loads(payload[start : end + 1])
        question_text = data["question_text"]
        options = [(o["label"], o["text"]) for o in data["options"]]
    except (json.JSONDecodeError, KeyError, TypeError) as exc:
        raise ProviderResponseError(
            f"correction reply was not a valid block: {exc}", provider=provider
        ) from exc
    if len(options) != len(original.options):
        raise ProviderResponseError("correction changed the number of options", provider=provider)
    return ParsedBlock(
        question_text=question_text,
        options=[
            Option(label=original.options[i].label, text=text)
            for i, (_label, text) in enumerate(options)
        ],
        raw_text=original.raw_text,
    )
