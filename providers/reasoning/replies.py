"""Shared reply parsing: correction JSON -> ParsedBlock, for every adapter."""

import json

from core.domain.errors import ProviderResponseError
from core.domain.models import Option, ParsedBlock
from core.services.block_parser import serialize


def parse_correction_reply(
    payload: str, original: ParsedBlock, provider: str, *, strict: bool = True
) -> ParsedBlock:
    start, end = payload.find("{"), payload.rfind("}")
    if start == -1 or end == -1 or end < start:
        raise ProviderResponseError("correction reply contained no JSON object", provider=provider)
    try:
        data = json.loads(payload[start : end + 1])
        question_text = data["question_text"]
        option_pairs = [(o["label"], o["text"]) for o in data["options"]]
    except (json.JSONDecodeError, KeyError, TypeError) as exc:
        raise ProviderResponseError(
            f"correction reply was not a valid block: {exc}", provider=provider
        ) from exc
    if strict and len(option_pairs) != len(original.options):
        raise ProviderResponseError("correction changed the number of options", provider=provider)
    if strict:
        # corrections may not relabel: the original labels are authoritative
        labels = [original.options[i].label for i in range(len(option_pairs))]
    else:
        labels = [label for label, _text in option_pairs]
    raw_text = original.raw_text if strict else _transcribed_text(question_text, option_pairs)
    return ParsedBlock(
        question_text=question_text,
        options=[
            Option(label=label, text=text)
            for label, (_label, text) in zip(labels, option_pairs, strict=True)
        ],
        raw_text=raw_text,
    )


def _transcribed_text(question_text: str, option_pairs: list[tuple[str, str]]) -> str:
    """Render a transcribed block as parser-acceptable text via the parser's
    own inverse — one canonical digit-label serialization."""
    block = ParsedBlock(
        question_text=question_text,
        options=[Option(label=label, text=text) for label, text in option_pairs],
        raw_text="",
    )
    return serialize(block)
