"""T2.1 — answer matcher: normalization, option matching, and letter strategies."""

import pytest

from core.domain.models import Option
from core.services.answer_matcher import fuzzy_matches, matches, resolve_letter

OPTIONS = [
    Option("A", "تهران"),
    Option("B", "مشهد"),
    Option("C", "اصفهان"),
    Option("D", "تبریز"),
]


def test_exact_latin_letter_matches() -> None:
    assert matches("C", OPTIONS)
    assert matches("c", OPTIONS)


def test_persian_digit_answer_normalized_to_match() -> None:
    # The model may echo the printed Persian label; ۳ is the third option.
    assert matches("۳", OPTIONS)
    assert matches("3", OPTIONS)


def test_diacritics_and_whitespace_ignored() -> None:
    assert matches("  C  ", OPTIONS)


def test_stray_punctuation_tolerated() -> None:
    assert matches("(C)", OPTIONS)
    assert matches("C.", OPTIONS)


def test_unrelated_answer_does_not_match() -> None:
    assert not matches("E", OPTIONS)
    assert not matches("تهران", OPTIONS)  # option text is not an option label


def test_fuzzy_matches_within_edit_distance_one() -> None:
    assert fuzzy_matches("C.", OPTIONS)  # stray trailing char
    assert fuzzy_matches("3", OPTIONS)  # digit-script difference is normalization, not fuzzy
    assert not fuzzy_matches("K", OPTIONS)


def test_resolve_letter_trust_model_returns_model_letter() -> None:
    assert resolve_letter("trust_model", "C", OPTIONS) == "C"
    assert resolve_letter("trust_model", "b", OPTIONS) == "B"


def test_resolve_letter_labels_then_position_uses_printed_label() -> None:
    # The model answered with a printed Persian label; map it positionally.
    assert resolve_letter("labels_then_position", "۳", OPTIONS) == "C"
    assert resolve_letter("labels_then_position", "ب", OPTIONS) == "B"


def test_resolve_letter_labels_then_position_falls_back_to_position() -> None:
    # Unparseable label but a valid letter: trust the letter's own position.
    assert resolve_letter("labels_then_position", "B", OPTIONS) == "B"


def test_resolve_letter_unmappable_returns_none() -> None:
    assert resolve_letter("trust_model", "wat", OPTIONS) is None
    assert resolve_letter("labels_then_position", "wat", OPTIONS) is None


def test_resolve_letter_rejects_unknown_strategy() -> None:
    with pytest.raises(ValueError) as err:
        resolve_letter("wat", "C", OPTIONS)  # type: ignore[arg-type]
    assert "trust_model" in str(err.value)
    assert "labels_then_position" in str(err.value)
