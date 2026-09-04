"""T1.1 — domain models: frozen dataclasses carrying the retry loop's vocabulary."""

import dataclasses

import pytest

from core.domain.models import BlockResult, Option, ParsedBlock, SolveAttempt


def test_option_holds_label_and_text() -> None:
    option = Option(label="A", text="پایتخت ایران")
    assert option.label == "A"
    assert option.text == "پایتخت ایران"


def test_option_label_normalized_uppercase() -> None:
    assert Option(label="b", text="x").label == "B"


def test_parsed_block_holds_question_options_raw() -> None:
    options = [Option("A", "x"), Option("B", "y")]
    block = ParsedBlock(question_text="کدام گزینه؟", options=options, raw_text="raw ocr")
    assert block.question_text == "کدام گزینه؟"
    assert block.options == options
    assert block.raw_text == "raw ocr"


def test_solve_attempt_holds_raw_answer_and_question_text() -> None:
    attempt = SolveAttempt(raw_answer="C", question_text_used="used text")
    assert attempt.raw_answer == "C"
    assert attempt.question_text_used == "used text"


def test_block_result_defaults_unresolved_false() -> None:
    result = BlockResult(answer="C", question_text="q", changed=False, original_ocr_text="o")
    assert result.unresolved is False


def test_block_result_defaults_attempts_one() -> None:
    result = BlockResult(answer="C", question_text="q", changed=False, original_ocr_text="o")
    assert result.attempts == 1


def test_domain_models_are_frozen() -> None:
    cases = [
        (Option("A", "x"), "text"),
        (ParsedBlock("q", [Option("A", "x")], "raw"), "question_text"),
        (SolveAttempt("A", "q"), "raw_answer"),
        (BlockResult("A", "q", False, "o"), "answer"),
    ]
    for instance, field_name in cases:
        with pytest.raises(dataclasses.FrozenInstanceError):
            setattr(instance, field_name, "mutated")
