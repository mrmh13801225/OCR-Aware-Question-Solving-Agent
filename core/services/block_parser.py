"""Parse raw OCR text into a ParsedBlock: question text plus positionally-labeled options.

Two passes. Pass 1 classifies whole lines: a line is an option when it starts
with a number (any digit script) or a Persian ordinal letter, followed by . )
or a stray RTL paren; anything else is question text — OCR noise lines
therefore degrade to the question, never to phantom options. Pass 2 (fallback,
only when pass 1 finds fewer than two options) re-scans for option markers in
the middle of a line: OCR engines occasionally emit every option on one
physical line (observed: datalab balance mode). Pass 2 never runs on a block
pass 1 already parsed, so question text containing (N) fragments is never
mis-split. Labels are assigned positionally (first match is A, second B, …):
the printed label is unreliable OCR output, while vertical order is stable, so
the number itself is matched but never used as a label.
"""

import re

from core.domain.errors import ParseError
from core.domain.models import OPTION_LABELS, Option, ParsedBlock

_DIGIT_OPTION_PATTERN = re.compile(r"^\(?\s*\d{1,2}\s*[)..]\s*(.+)$")
_RTL_PAREN_PATTERN = re.compile(r"^\(\s*\d{1,2}\s+(.+)$")
_LETTER_OPTION_PATTERN = re.compile(r"^(الف|ب|ج|د)\s*[).]\s*(.+)$")
_LETTER_TO_LABEL = {"الف": "A", "ب": "B", "ج": "C", "د": "D"}

# An option marker mid-line: whitespace (or string start), then the same
# number+separator shape pass 1 accepts. The lookbehind keeps `(0, k)` and
# `(2k+2` (comma/letter after the paren) and `=1.0` (no boundary) out.
_INLINE_MARKER_PATTERN = re.compile(r"(?:^|(?<=\s))\(?\s*\d{1,2}\s*[)..]\s*")

_MAX_OPTIONS = len(OPTION_LABELS)


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


def _split_inline(line: str) -> tuple[str, list[str]]:
    """(leading_text, option_texts) from the markers inside one line.

    leading_text is whatever precedes the first marker (question fragment, or
    "" when the line starts with one); option_texts are the marker bodies,
    sliced from the ORIGINAL line so their text survives. Markers are located
    on a math-blanked copy: LaTeX like `(m^2 + 2m - 1)` contains `- 1)`,
    which the marker pattern would otherwise read as an option marker. A
    trailing marker with no body after it is dropped, not turned into an
    empty option.
    """
    blanked = _blank_math_spans(line)
    marker_spans = [
        (m.start(), m.end()) for m in _INLINE_MARKER_PATTERN.finditer(blanked)
    ]
    if not marker_spans:
        return line.strip(), []
    leading = line[: marker_spans[0][0]].strip()
    bodies = []
    for i, (_start, end) in enumerate(marker_spans):
        next_start = marker_spans[i + 1][0] if i + 1 < len(marker_spans) else len(line)
        body = line[end:next_start].strip()
        if body:
            bodies.append(body)
    return leading, bodies


_MATH_SPAN_PATTERN = re.compile(r"<math>.*?</math>|\$[^$]*\$", re.DOTALL)
_MATH_PLACEHOLDER = "\x00"


def _blank_math_spans(line: str) -> str:
    """Replace every math-span character with a placeholder, one-for-one.

    Length-preserving so marker positions found on the blanked copy index
    directly into the original line; a non-whitespace placeholder so the
    marker pattern's \\s* cannot run across a span (gluing it to the
    preceding marker).
    """
    return _MATH_SPAN_PATTERN.sub(lambda m: _MATH_PLACEHOLDER * len(m.group()), line)


def _classify(
    lines: list[str], split_bodies: bool, raw_text: str
) -> tuple[list[str], list[Option]]:
    """Shared classification for both passes: question lines + collected options.

    split_bodies=False is pass 1: each line yields at most one option.
    split_bodies=True is pass 2: an option line whose body still contains
    markers, and any non-option line containing markers, contributes several.
    """
    question_lines: list[str] = []
    options: list[Option] = []

    def add_option(text: str) -> None:
        if len(options) >= _MAX_OPTIONS:
            raise ParseError(f"more than {_MAX_OPTIONS} options", raw_text=raw_text)
        options.append(Option(label=OPTION_LABELS[len(options)], text=text))

    for line in lines:
        matched = _option_body(line)
        if matched is None:
            leading, texts = _split_inline(line) if split_bodies else ("", [])
            if texts:
                if leading:
                    question_lines.append(leading)
                for text in texts:
                    add_option(text)
            else:
                question_lines.append(line.strip())
            continue
        _label_override, body = matched
        if split_bodies:
            leading, texts = _split_inline(line)
            # the whole-line match swallowed later markers; re-split from the
            # line start so the first option's body is not lost
            if len(texts) > 1 or (len(texts) == 1 and leading):
                if leading:
                    question_lines.append(leading)
                for text in texts:
                    add_option(text)
                continue
        add_option(body)

    return question_lines, options


def parse(raw_text: str) -> ParsedBlock:
    """Split raw OCR text into question text and options.

    Labels are normalized positionally: the first matched option line is A,
    the second B, and so on — regardless of the label style the scan printed.
    Line-wise first; the inline split only rescues blocks the line-wise pass
    could not read (fewer than two options), never reworks ones it did.
    """
    lines = raw_text.splitlines()

    question_lines, options = _classify(lines, split_bodies=False, raw_text=raw_text)
    if len(options) < 2:
        question_lines, options = _classify(lines, split_bodies=True, raw_text=raw_text)

    question_text = "\n".join(line for line in question_lines if line)
    if not question_text or len(options) < 2:
        raise ParseError("could not find a question with at least two options", raw_text=raw_text)
    return ParsedBlock(question_text=question_text, options=options, raw_text=raw_text)


def serialize(block: ParsedBlock) -> str:
    """Inverse of parse(): the canonical text form, with digit option labels.

    `Option.label` (A/B/C/D) is the loop's internal vocabulary; `raw_text` is
    a faithful rendition of the block as text, so options serialize as
    1) 2) 3) 4) — the digit style parse() accepts for every script.
    """
    option_lines = [f"{i}) {o.text}" for i, o in enumerate(block.options, start=1)]
    return "\n".join([block.question_text, *option_lines])
