"""Parse raw OCR text into a ParsedBlock: question text plus positionally-labeled options."""

import re

from core.domain.errors import ParseError
from core.domain.models import Option, ParsedBlock

_PERSIAN_DIGITS = "۰۱۲۳۴۵۶۷۸۹"
_ARABIC_DIGITS = "٠١٢٣٤٥٦٧٨٩"

_PERSIAN_LETTER_LABELS = {"الف": "A", "ب": "B", "ج": "C", "د": "D", "الف)": "A"}


def _normalize_label_digits(label: str) -> str:
    table = str.maketrans(_PERSIAN_DIGITS + _ARABIC_DIGITS, "0123456789" * 2)
    return label.translate(table)


# A line is an option when it starts with a number (any digit script) or a
# Persian ordinal letter, followed by . ) or a stray RTL paren. Anything else
# is question text — OCR noise lines therefore degrade to the question, never
# to phantom options.
_OPTION_PATTERNS: list[re.Pattern[str]] = [
    re.compile(r"^\(?\s*(\d{1,2})\s*[)..]\s+(.+)$"),
    re.compile(r"^\(?\s*(\d{1,2})\s*[)..]\s*(.+)$"),
    re.compile(r"^\(\s*(\d{1,2})\s+(.+)$"),
]

_LETTER_PATTERN = re.compile(r"^(الف|ب|ج|د)\s*[).]\s*(.+)$")


def _match_option_line(line: str) -> tuple[str, str] | None:
    stripped = line.strip()
    if not stripped:
        return None
    for pattern in _OPTION_PATTERNS:
        match = pattern.match(stripped)
        if match:
            return _normalize_label_digits(match.group(1)), match.group(2).strip()
    letter_match = _LETTER_PATTERN.match(stripped)
    if letter_match:
        return _PERSIAN_LETTER_LABELS[letter_match.group(1)], letter_match.group(2).strip()
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
        matched = _match_option_line(line)
        if matched is None:
            question_lines.append(line.strip())
            continue
        options.append(Option(label=_next_label(len(options)), text=matched[1]))

    question_text = "\n".join(line for line in question_lines if line)
    if not question_text or len(options) < 2:
        raise ParseError("could not find a question with at least two options", raw_text=raw_text)
    return ParsedBlock(question_text=question_text, options=options, raw_text=raw_text)


_LABELS = "ABCDEFGH"


def _next_label(index: int) -> str:
    if index >= len(_LABELS):
        raise ParseError("more options than supported labels", raw_text="")
    return _LABELS[index]
