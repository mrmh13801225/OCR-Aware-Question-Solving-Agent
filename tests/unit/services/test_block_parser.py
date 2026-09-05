"""T1.4 — block parser: raw OCR text -> ParsedBlock (question + options)."""

import pytest

from core.domain.errors import ParseError
from core.domain.models import Option, ParsedBlock
from core.services.block_parser import parse, serialize

LATIN = "Which option is correct?\n1) alpha\n2) beta\n3) gamma\n4) delta"
PERSIAN_DIGITS = "در تصویر مقابل کدام است؟\n۱) الف\n۲) ب\n۳) ج\n۴) د"
ARABIC_DIGITS = "السؤال هنا؟\n١) أ\n٢) ب\n٣) ج\n٤) د"
DOT_NUMBERED = "کدام گزینه درست است؟\n1. الف\n2. ب\n3. ج\n4. د"
PERSIAN_DOT_NUMBERED = "کدام گزینه درست است؟\n۱. الف\n۲. ب\n۳. ج\n۴. د"
PERSIAN_LETTERS = "نتیجه کدام است؟\nالف) یکی\nب) دو\nج) سه\nد) چهار"
RTL_PAREN = "پرسش این است؟\n(۱ یکی\n(۲ دو\n(۳ سه\n(۴ چهار"


def _labels(block: ParsedBlock) -> list[str]:
    return [o.label for o in block.options]


def _texts(block: ParsedBlock) -> list[str]:
    return [o.text for o in block.options]


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


def test_parses_persian_dot_numbered_options() -> None:
    # TESTING.md §0.5: the ۱. (Persian digit + dot) variant the scans print.
    block = parse(PERSIAN_DOT_NUMBERED)
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


def test_serialize_round_trips_through_parse() -> None:
    for raw in (LATIN, PERSIAN_DIGITS, PERSIAN_LETTERS, RTL_PAREN):
        block = parse(raw)
        rendered = parse(serialize(block))
        assert rendered.question_text == block.question_text
        assert [o.text for o in rendered.options] == [o.text for o in block.options]
        assert [o.label for o in rendered.options] == [o.label for o in block.options]


def test_serialize_uses_digit_labels_not_internal_abcd() -> None:
    block = parse(PERSIAN_DIGITS)
    text = serialize(block)
    assert "1)" in text and "A)" not in text


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
    raw = "فقط یک سؤال بدون گزینه"
    with pytest.raises(ParseError) as err:
        parse(raw)
    assert err.value.raw_text == raw  # the offending text travels with the error


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


# --- inline option rows: OCR engines sometimes emit every option on one line ---


DATALAB_BALANCE_MODE = (
    "۱۱۳- تابع  $f(x) = mx^2 - nx - k$  در هر بازه، هم صعودی و هم نزولی است. "
    "اگر مجموعه زیر، تابع باشد، مقدار\n\n"
    "$f(\\sqrt{5})$  کدام است؟  $\\{(m, n-1), (0, k), (n-1, m^2 + 2m - 1), (2k+2, 2k+1)\\}$\n\n"
    "(۱) ۱ (۲)  $-\\sqrt{5}$  (۳) ۱ (۴)  $\\sqrt{5}$"
)


def test_parses_all_options_on_one_physical_line() -> None:
    block = parse(DATALAB_BALANCE_MODE)
    assert [o.label for o in block.options] == ["A", "B", "C", "D"]
    assert [o.text for o in block.options] == ["۱", "$-\\sqrt{5}$", "۱", "$\\sqrt{5}$"]
    assert "کدام است؟" in block.question_text
    assert "(m, n-1)" in block.question_text  # the set stays in the question, unsplit
    assert block.raw_text == DATALAB_BALANCE_MODE


# The exact /api/v1/marker output for the same scan (live-verified): the
# options arrive as a markdown list, one per line, bullet + paren marker.
DATALAB_BALANCE_MODE_MARKER_LIVE = (
    "۱۱۳- تابع  $f(x) = mx^2 - nx - k$  در هر بازه، هم صعودی و هم نزولی است. "
    "اگر مجموعه زیر، تابع باشد، مقدار\n\n"
    "$f(\\sqrt{5})$  کدام است؟  $\\{(m, n-1), (0, k), (n-1, m^2 + 2m - 1), (2k+2, 2k+1)\\}$\n\n"
    "- (۱) ۱\n"
    "- (۲)  $-\\sqrt{5}$\n"
    "- (۳) ۱\n"
    "- (۴)  $\\sqrt{5}$"
)


def test_parses_the_live_marker_bullet_form() -> None:
    block = parse(DATALAB_BALANCE_MODE_MARKER_LIVE)
    assert [o.label for o in block.options] == ["A", "B", "C", "D"]
    assert [o.text for o in block.options] == ["۱", "$-\\sqrt{5}$", "۱", "$\\sqrt{5}$"]
    assert "کدام است؟" in block.question_text
    assert "(n-1" in block.question_text  # the math set stays in the question
    assert block.raw_text == DATALAB_BALANCE_MODE_MARKER_LIVE


def test_parses_latin_inline_option_row() -> None:
    block = parse("Which is it?\n(1) alpha (2) beta (3) gamma (4) delta")
    assert _labels(block) == ["A", "B", "C", "D"]
    assert _texts(block) == ["alpha", "beta", "gamma", "delta"]
    assert block.question_text == "Which is it?"


def test_parses_fully_inline_single_line_block() -> None:
    block = parse("question? (1) x (2) y (3) z (4) w")
    assert block.question_text == "question?"
    assert _texts(block) == ["x", "y", "z", "w"]


def test_question_fragments_are_never_split_when_the_block_parses_line_wise() -> None:
    raw = "مقدار $f(2)$ چقدر است؟\n1) x\n2) y"
    block = parse(raw)
    assert block.question_text == "مقدار $f(2)$ چقدر است؟"
    assert _texts(block) == ["x", "y"]


def test_text_without_any_option_marker_still_raises() -> None:
    with pytest.raises(ParseError) as err:
        parse("فقط یک سؤال بدون گزینه با (1) چیزی شبیه مارکر ولی بدون بدنه")
    assert "could not find a question with at least two options" in str(err.value)


def test_inline_block_round_trips_through_serialize() -> None:
    block = parse(DATALAB_BALANCE_MODE)
    rendered = parse(serialize(block))
    assert [o.text for o in rendered.options] == [o.text for o in block.options]
    assert [o.label for o in rendered.options] == [o.label for o in block.options]
