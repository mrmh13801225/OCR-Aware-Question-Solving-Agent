"""Parse raw OCR text into a ParsedBlock: question text plus positionally-labeled options."""

import re

from core.domain.errors import ParseError
from core.domain.models import Option, ParsedBlock

# A line is an option when it starts with a number (any digit script) or a
# Persian ordinal letter, followed by . ) or a stray RTL paren. Anything else
# is question text — OCR noise lines therefore degrade to the question, never
# to phantom options. Labels are assigned positionally (first match is A,
# second B, …): the printed label is unreliable OCR output, while vertical
# order is stable, so the number itself is matched but never used as a label.
_DIGIT_OPTION_PATTERN = re.compile(r"^\(?\s*\d{1,2}\s*[)..]\s*(.+)$")
_RTL_PAREN_PATTERN = re.compile(r"^\(\s*\d{1,2}\s+(.+)$")
_LETTER_OPTION_PATTERN = re.compile(r"^(الف|ب|ج|د)\s*[).]\s*(.+)$")
_LETTER_TO_LABEL = {"الف": "A", "ب": "B", "ج": "C", "د": "D"}

LABELS = "ABCDEFGH"
_MAX_OPTIONS = len(LABELS)


def _option_body(line: str) -> tuple[str, str] | None:
    """Return (label_override_or_empty, option_text) when the line is an option."""
    stripped = line.strip()
    if not stripped:
        return None
    digit_match = _DIGIT_OPTION_PATTERN.match(stripped)
    if digit_match:
        return "", digit_match.group(1).strip()
    rtl_match = _RTL_PAREN_PATTERN.match(stripped)
    if rtl_match:
        return "", rtl_match.group(1).strip()
    letter_match = _LETTER_OPTION_PATTERN.match(stripped)
    if letter_match:
        return _LETTER_TO_LABEL[letter_match.group(1)], letter_match.group(2).strip()
    return None


def parse(raw_text: str) -> ParsedBlock:
    """Split raw OCR text into question text and options.

    Labels are normalized positionally: the first matched option line is A,
    the second B, and so on — regardless of the label style the scan printed.
    """
    lines = raw_text.splitlines()
    question_lines: list[str] = []
    options: list[Option] = []

    for line in lines:
        matched = _option_body(line)
        if matched is None:
            question_lines.append(line.strip())
            continue
        if len(options) >= _MAX_OPTIONS:
            raise ParseError(f"more than {_MAX_OPTIONS} options", raw_text=raw_text)
        options.append(Option(label=LABELS[len(options)], text=matched[1]))

    question_text = "\n".join(line for line in question_lines if line)
    if not question_text or len(options) < 2:
        raise ParseError("could not find a question with at least two options", raw_text=raw_text)
    return ParsedBlock(question_text=question_text, options=options, raw_text=raw_text)
