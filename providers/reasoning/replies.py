"""Shared reply parsing: correction JSON -> ParsedBlock, for every adapter."""

import json

from core.domain.errors import ProviderResponseError
from core.domain.models import Option, ParsedBlock


def parse_correction_reply(
    payload: str, original: ParsedBlock, provider: str, *, strict: bool = True
) -> ParsedBlock:
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
    if strict and len(options) != len(original.options):
        raise ProviderResponseError("correction changed the number of options", provider=provider)
    if strict:
        # corrections may not relabel: the original labels are authoritative
        labels = [original.options[i].label for i in range(len(options))]
    else:
        labels = [label for label, _text in options]
    raw_text = original.raw_text if strict else serialize_text(question_text, options)
    return ParsedBlock(
        question_text=question_text,
        options=[
            Option(label=label, text=text)
            for label, (_l, text) in zip(labels, options, strict=True)
        ],
        raw_text=raw_text,
    )


def serialize_text(question_text: str, options: list[tuple[str, str]]) -> str:
    """Render a transcribed block as text the parser accepts (digit labels)."""
    option_lines = [f"{i}) {text}" for i, (_label, text) in enumerate(options, start=1)]
    return "\n".join([question_text, *option_lines])
