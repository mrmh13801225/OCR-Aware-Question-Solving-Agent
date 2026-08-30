"""Normalize model answers and match them against a block's options.

Matching is deliberately strict: the primary check must not be lenient, or
over-matching would defeat the OCR-error-detection criterion (a mismatch is
the evidence that drives the retry loop). Fuzzy matching exists only for the
unresolved path in best_guess.
"""

import unicodedata

from core.domain.models import Option

_PERSIAN_DIGITS = "۰۱۲۳۴۵۶۷۸۹"
_ARABIC_DIGITS = "٠١٢٣٤٥٦٧٨٩"
_TO_LATIN_DIGITS = str.maketrans(_PERSIAN_DIGITS + _ARABIC_DIGITS, "0123456789" * 2)

_LETTER_TO_INDEX = {chr(ord("A") + i): i for i in range(8)}
_PERSIAN_LETTER_TO_INDEX = {"الف": 0, "ب": 1, "ج": 2, "د": 3}


def normalize(text: str) -> str:
    """Canonical form: Latin digits, stripped marks/whitespace/punctuation."""
    text = unicodedata.normalize("NFKC", text).translate(_TO_LATIN_DIGITS)
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    return "".join(ch for ch in text if not ch.isspace() and unicodedata.category(ch)[0] != "P")


def _normalized_label_index(raw_answer: str) -> int | None:
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
    index = _normalized_label_index(raw_answer)
    return index is not None and 0 <= index < len(options)


def fuzzy_matches(raw_answer: str, options: list[Option]) -> bool:
    """Lenient check — unresolved path only.

    A strict index lookup fails on stray characters ("C." vs C) or OCR-swapped
    letter forms ("G" read for C). Fuzzy tolerance means: drop or swap at most
    one character and re-check the label vocabulary. Free-string edit distance
    is deliberately NOT used — every single-letter string would then be within
    distance 1 of every one-letter label.
    """
    if matches(raw_answer, options):
        return True
    normalized = normalize(raw_answer).upper()
    for i in range(len(normalized)):
        if _normalized_label_index(normalized[:i] + normalized[i + 1 :]) is not None:
            return True
    for _from, to in _CONFUSABLE_LETTERS:
        if to == normalized and _normalized_label_index(_from) is not None:
            return True
    return False


# OCR reads one letter form as its visually confusable neighbor; a stray mark
# is handled by the deletion pass above.
_CONFUSABLE_LETTERS: list[tuple[str, str]] = [
    ("C", "G"),
    ("G", "C"),
    ("O", "D"),
    ("D", "O"),
    ("B", "E"),
    ("E", "B"),
]


def resolve_fuzzy_letter(raw_answer: str, options: list[Option]) -> str | None:
    """Letter for an answer only the fuzzy tier accepts; None if truly unmappable."""
    index = _normalized_label_index(raw_answer)
    if index is None or not 0 <= index < len(options):
        # Out-of-range strict mappings (G for a 4-option block) fall through to
        # the confusable table: OCR reads C as G, not as option G.
        normalized = normalize(raw_answer).upper()
        index = next(
            (_LETTER_TO_INDEX[_from] for _from, to in _CONFUSABLE_LETTERS if to == normalized),
            None,
        )
    if index is None or not 0 <= index < len(options):
        return None
    return options[index].label


def resolve_letter(strategy: str, raw_answer: str, options: list[Option]) -> str | None:
    """Map a raw model answer to the output letter under the chosen strategy.

    trust_model: the model is prompted to answer A–D; its validated letter is
    the output verbatim. labels_then_position: printed labels (Persian digits
    or ordinal letters) map positionally; a Latin letter falls back to its own
    position. Anything unmappable yields None — callers surface unresolved.
    """
    index = _normalized_label_index(raw_answer)
    if index is None or not 0 <= index < len(options):
        return None
    if strategy == "trust_model" and normalized_is_letter(raw_answer):
        return normalize(raw_answer).upper()
    return options[index].label


def normalized_is_letter(raw_answer: str) -> bool:
    return normalize(raw_answer) in _LETTER_TO_INDEX
