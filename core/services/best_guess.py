"""Tiered best-guess selection when the retry loop caps out without a match."""

from collections import Counter

from core.domain.models import Option, SolveAttempt
from core.services.answer_matcher import (
    _normalized_label_index,
    fuzzy_matches,
    resolve_fuzzy_letter,
)


def pick_best(attempts: list[SolveAttempt], options: list[Option]) -> str:
    """Pick the output letter for an unresolved block, in declared tier order.

    1. Fuzzy re-check: an answer the strict check rejected but fuzzy accepts
       (confusable letter) — earliest attempt wins.
    2. Majority vote: the most common answer across attempts, if one exists.
    3. First attempt: the least-mutated text is the most grounded read.
    """
    for attempt in attempts:
        letter = resolve_fuzzy_letter(attempt.raw_answer, options)
        if letter is not None and fuzzy_matches(attempt.raw_answer, options):
            return letter

    counts = Counter(a.raw_answer for a in attempts)
    answer, count = counts.most_common(1)[0]
    if count > 1:
        return _letter(answer, options)

    return _letter(attempts[0].raw_answer, options)


def _letter(raw_answer: str, options: list[Option]) -> str:
    index = _normalized_label_index(raw_answer)
    if index is not None and 0 <= index < len(options):
        return options[index].label
    return options[0].label
