"""T2.2 — tiered best-guess selection for the unresolved path."""

from core.domain.models import Option, SolveAttempt
from core.services.best_guess import pick_best

OPTIONS = [
    Option("A", "تهران"),
    Option("B", "مشهد"),
    Option("C", "اصفهان"),
    Option("D", "تبریز"),
]


def _attempt(answer: str, index: int = 0) -> SolveAttempt:
    return SolveAttempt(raw_answer=answer, question_text_used="q")


def test_tier1_fuzzy_recheck_finds_near_miss() -> None:
    # No strict match, but "C." is within fuzzy tolerance of option C.
    attempts = [_attempt("C."), _attempt("Z")]
    assert pick_best(attempts, OPTIONS) == "C"


def test_tier1_prefers_earliest_attempt() -> None:
    attempts = [_attempt("Z"), _attempt("D.")]
    assert pick_best(attempts, OPTIONS) == "D"


def test_tier1_drop_one_character_pass_rescues_surviving_stray_mark() -> None:
    # Punctuation strays are stripped by strict normalization; a digit or letter
    # glued to the label survives it and needs the drop-one-character tier.
    attempts = [_attempt("4C"), _attempt("Z")]
    assert pick_best(attempts, OPTIONS) == "C"


def test_tier1_drop_one_character_pass_rescues_persian_stray() -> None:
    attempts = [_attempt("کC")]
    assert pick_best(attempts, OPTIONS) == "C"


def test_tier2_majority_vote_picks_plurality() -> None:
    attempts = [_attempt("A", 0), _attempt("A", 1), _attempt("B", 2)]
    assert pick_best(attempts, OPTIONS) == "A"


def test_tier3_falls_back_to_first_attempt() -> None:
    attempts = [_attempt("B", 0), _attempt("D", 1)]
    # No fuzzy match, no plurality (1-1 tie) -> first attempt's letter.
    assert pick_best(attempts, OPTIONS) == "B"


def test_tier2_garbage_majority_degrades_to_first_option() -> None:
    # Unresolved precondition: no attempt strict-matched. A mappable letter
    # (A-D, digits) would have ended the loop, so a majority of raw answers
    # here is garbage; the declared tier-2 method fires but yields no letter,
    # degrading to the first-option fallback.
    attempts = [_attempt("Z", 0), _attempt("K", 1), _attempt("K", 2)]
    assert pick_best(attempts, OPTIONS) == "A"


def test_tier3_no_majority_degrades_to_first_option() -> None:
    attempts = [_attempt("Z", 0), _attempt("K", 1)]
    assert pick_best(attempts, OPTIONS) == "A"


def test_tier1_beats_later_plurality() -> None:
    # One fuzzy-rescued attempt wins regardless of later repeats.
    attempts = [_attempt("Z"), _attempt("C."), _attempt("C.", 1)]
    assert pick_best(attempts, OPTIONS) == "C"


def test_unmappable_answers_fall_through_to_first_attempt() -> None:
    attempts = [_attempt("wat", 0), _attempt("huh", 1)]
    assert pick_best(attempts, OPTIONS) == "A"
