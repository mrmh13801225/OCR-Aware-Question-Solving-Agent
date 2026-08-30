"""T1.4 — block parser: raw OCR text -> ParsedBlock (question + options)."""

import pytest

from core.domain.errors import ParseError
from core.domain.models import Option
from core.services.block_parser import parse

LATIN = "Which option is correct?\n1) alpha\n2) beta\n3) gamma\n4) delta"
PERSIAN_DIGITS = "در تصویر مقابل کدام است؟\n۱) الف\n۲) ب\n۳) ج\n۴) د"
ARABIC_DIGITS = "السؤال هنا؟\n١) أ\n٢) ب\n٣) ج\n٤) د"
DOT_NUMBERED = "کدام گزینه درست است؟\n1. الف\n2. ب\n3. ج\n4. د"
PERSIAN_LETTERS = "نتیجه کدام است؟\nالف) یکی\nب) دو\nج) سه\nد) چهار"
RTL_PAREN = "پرسش این است؟\n(۱ یکی\n(۲ دو\n(۳ سه\n(۴ چهار"


def _labels(block: object) -> list[str]:
    return [o.label for o in block.options]  # type: ignore[attr-defined]


def _texts(block: object) -> list[str]:
    return [o.text for o in block.options]  # type: ignore[attr-defined]


def test_parses_question_and_four_options() -> None:
    block = parse(LATIN)
    assert block.question_text == "Which option is correct?"
    assert _labels(block) == ["A", "B", "C", "D"]
    assert _texts(block) == ["alpha", "beta", "gamma", "delta"]
    assert block.raw_text == LATIN


def test_parses_persian_digit_labels() -> None:
    block = parse(PERSIAN_DIGITS)
    assert block.question_text == "در تصویر مقابل کدام است؟"
    assert _labels(block) == ["A", "B", "C", "D"]
    assert _texts(block) == ["الف", "ب", "ج", "د"]


def test_parses_arabic_digit_labels() -> None:
    block = parse(ARABIC_DIGITS)
    assert _labels(block) == ["A", "B", "C", "D"]
    assert _texts(block) == ["أ", "ب", "ج", "د"]


def test_parses_dot_numbered_options() -> None:
    block = parse(DOT_NUMBERED)
    assert _labels(block) == ["A", "B", "C", "D"]
    assert _texts(block) == ["الف", "ب", "ج", "د"]


def test_parses_persian_letter_labels() -> None:
    block = parse(PERSIAN_LETTERS)
    assert _labels(block) == ["A", "B", "C", "D"]
    assert _texts(block) == ["یکی", "دو", "سه", "چهار"]


def test_parses_rtl_parenthesis_variants() -> None:
    block = parse(RTL_PAREN)
    assert _labels(block) == ["A", "B", "C", "D"]
    assert _texts(block) == ["یکی", "دو", "سه", "چهار"]


def test_labels_normalized_to_abcd_positionally() -> None:
    block = parse(PERSIAN_DIGITS)
    assert _labels(block) == ["A", "B", "C", "D"]


def test_non_option_lines_join_question_text() -> None:
    raw = "متن سؤال اول\nادامه سؤال؟\n۱) الف\n۲) ب\n۳) ج\n۴) د\nپانویس تصادفی"
    block = parse(raw)
    assert "متن سؤال اول" in block.question_text
    assert "ادامه سؤال" in block.question_text
    assert "پانویس تصادفی" in block.question_text
    assert len(block.options) == 4


def test_multiline_question_preserved() -> None:
    raw = "خط اول\nخط دوم؟\n1) x\n2) y\n3) z\n4) w"
    block = parse(raw)
    assert block.question_text == "خط اول\nخط دوم؟"


def test_empty_text_raises_parse_error() -> None:
    with pytest.raises(ParseError) as err:
        parse("   \n  ")
    assert err.value.raw_text == "   \n  "


def test_no_options_raises_parse_error() -> None:
    with pytest.raises(ParseError):
        parse("فقط یک سؤال بدون گزینه")


def test_too_many_options_raises_parse_error_carrying_raw_text() -> None:
    raw = "q?\n" + "\n".join(f"{i}) x{i}" for i in range(1, 10))
    with pytest.raises(ParseError) as err:
        parse(raw)
    assert err.value.raw_text == raw


def test_parser_does_not_alter_option_text() -> None:
    raw = "؟\n1) x  y\n2) z\n3) w\n4) v"
    block = parse(raw)
    assert _texts(block) == ["x  y", "z", "w", "v"]


def test_option_positions_map_by_appearance_order() -> None:
    block = parse("q?\n۱) اول\n۲) دوم\n۳) سوم\n۴) چهارم")
    assert block.options == [
        Option("A", "اول"),
        Option("B", "دوم"),
        Option("C", "سوم"),
        Option("D", "چهارم"),
    ]
