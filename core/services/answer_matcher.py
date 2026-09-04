"""Normalize model answers and match them against a block's options.

Matching is deliberately strict: the primary check must not be lenient, or
over-matching would defeat the OCR-error-detection criterion (a mismatch is
the evidence that drives the retry loop). Fuzzy matching exists only for the
unresolved path in best_guess.
"""

import unicodedata

from core.domain.models import OPTION_LABELS, AnswerMapping, Option

_PERSIAN_DIGITS = "۰۱۲۳۴۵۶۷۸۹"
_ARABIC_DIGITS = "٠١٢٣٤٥٦٧٨٩"
_TO_LATIN_DIGITS = str.maketrans(_PERSIAN_DIGITS + _ARABIC_DIGITS, "0123456789" * 2)

_LETTER_TO_INDEX = {label: i for i, label in enumerate(OPTION_LABELS)}
_PERSIAN_LETTER_TO_INDEX = {"الف": 0, "ب": 1, "ج": 2, "د": 3}


def normalize(text: str) -> str:
    """Canonical form: Latin digits, stripped marks/whitespace/punctuation."""
    # NFKD (decompose, no recompose) — NFKC would fuse base+mark into a
    # precomposed letter (C + U+0301 -> Ć) that the strip pass can't see.
    text = unicodedata.normalize("NFKD", text).translate(_TO_LATIN_DIGITS)
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    return "".join(ch for ch in text if not ch.isspace() and unicodedata.category(ch)[0] != "P")


def normalized_label_index(raw_answer: str) -> int | None:
    """Map a raw answer (letter, Persian/Arabic ordinal, or digit) to an option index."""
    normalized = normalize(raw_answer).upper()
    if normalized in _LETTER_TO_INDEX:
        return _LETTER_TO_INDEX[normalized]
    if normalized in _PERSIAN_LETTER_TO_INDEX:
        return _PERSIAN_LETTER_TO_INDEX[normalized]
    if normalized.isdigit():
        index = int(normalized) - 1
        if 0 <= index < len(_LETTER_TO_INDEX):
            return index
    return None


def matches(raw_answer: str, options: list[Option]) -> bool:
    """True when the answer identifies one of the options (letter or ordinal)."""
    index = normalized_label_index(raw_answer)
    return index is not None and 0 <= index < len(options)


# OCR reads one letter form as its visually confusable neighbor: (read, printed).
_CONFUSABLE_LETTERS: list[tuple[str, str]] = [
    ("C", "G"),
    ("G", "C"),
    ("O", "D"),
    ("D", "O"),
    ("B", "E"),
    ("E", "B"),
]


def fuzzy_index(normalized_answer: str, option_count: int) -> int | None:
    """Index for an answer only fuzzy tolerance accepts; None if unmappable.

    Tiers, in declared order (DESIGN.md §7): strict lookup, then a
    drop-one-character re-check (a stray mark glued to the label survives
    normalization — "4C" or "کC"), then the visually-confusable letter table.
    An index outside the block's option range falls through to the next tier:
    OCR reads C as G, not as option G. Free-string edit distance is
    deliberately NOT used — every single-letter string would be within
    distance 1 of every one-letter label.
    """
    index = _strict_index(normalized_answer, option_count)
    if index is not None:
        return index
    index = _deletion_index(normalized_answer, option_count)
    if index is not None:
        return index
    return _confusable_index(normalized_answer, option_count)


def resolve_fuzzy_letter(raw_answer: str, options: list[Option]) -> str | None:
    """Letter for an answer only the fuzzy tier accepts; None if truly unmappable."""
    index = fuzzy_index(normalize(raw_answer).upper(), len(options))
    if index is None:
        return None
    return options[index].label


def _in_range(index: int | None, option_count: int) -> bool:
    return index is not None and 0 <= index < option_count


def _strict_index(normalized: str, option_count: int) -> int | None:
    index = normalized_label_index(normalized)
    return index if _in_range(index, option_count) else None


def _deletion_index(normalized: str, option_count: int) -> int | None:
    for i in range(len(normalized)):
        index = normalized_label_index(normalized[:i] + normalized[i + 1 :])
        if _in_range(index, option_count):
            return index
    return None


def _confusable_index(normalized: str, option_count: int) -> int | None:
    for letter, confusable in _CONFUSABLE_LETTERS:
        if confusable != normalized:
            continue
        index = normalized_label_index(letter)
        if _in_range(index, option_count):
            return index
    return None


def resolve_letter(strategy: AnswerMapping, raw_answer: str, options: list[Option]) -> str | None:
    """Map a raw model answer to the output letter under the chosen strategy.

    trust_model: the model is prompted to answer A–D; its validated letter is
    the output verbatim. labels_then_position: printed labels (Persian digits
    or ordinal letters) map positionally; a Latin letter falls back to its own
    position. Anything unmappable yields None — callers surface unresolved.
    Unknown strategies raise: silently treating one as labels_then_position
    would hide config mistakes.
    """
    index = normalized_label_index(raw_answer)
    if index is None or not 0 <= index < len(options):
        return None
    if strategy == "trust_model":
        if normalized_is_letter(raw_answer):
            return normalize(raw_answer).upper()
        return options[index].label
    if strategy == "labels_then_position":
        return options[index].label
    raise ValueError(
        f"Unknown answer mapping strategy '{strategy}'. "
        f"Valid options: trust_model, labels_then_position."
    )


def normalized_is_letter(raw_answer: str) -> bool:
    return normalize(raw_answer) in _LETTER_TO_INDEX
