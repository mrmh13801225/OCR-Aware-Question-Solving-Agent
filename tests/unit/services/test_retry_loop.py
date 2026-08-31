"""T2.3 — the retry loop: scripted fake providers, full state matrix, events."""

from dataclasses import dataclass, field

from core.domain.models import Option, ParsedBlock, SolveAttempt
from core.domain.ports import OCRText, RunEvent
from core.services.noise_injector import NoiseInjector
from core.services.retry_loop import RetryLoop

OPTIONS = [
    Option("A", "تهران"),
    Option("B", "مشهد"),
    Option("C", "اصفهان"),
    Option("D", "تبریز"),
]

RAW_TEXT = "کدام شهر؟\n۱) تهران\n۲) مشهد\n۳) اصفهان\n۴) تبریز"


@dataclass
class FakeOCR:
    text: str = RAW_TEXT
    calls: int = 0

    def extract_text(self, image: bytes) -> OCRText:
        self.calls += 1
        return OCRText(text=self.text, provider="fake")


@dataclass
class ScriptedReasoning:
    """Answers in sequence; corrections in sequence; records every call."""

    answers: list[str]
    corrections: list[ParsedBlock] = field(default_factory=list)
    solve_calls: int = 0
    correct_calls: int = 0
    seen_images: list[bytes] = field(default_factory=list)
    seen_questions: list[str] = field(default_factory=list)
    seen_failed: list[str] = field(default_factory=list)

    def solve(self, image: bytes, question_text: str, options: list[Option]) -> SolveAttempt:
        self.solve_calls += 1
        self.seen_images.append(image)
        self.seen_questions.append(question_text)
        answer = self.answers[min(self.solve_calls - 1, len(self.answers) - 1)]
        return SolveAttempt(
            raw_answer=answer, question_text_used=question_text, attempt_index=self.solve_calls - 1
        )

    def correct(self, image: bytes, block: ParsedBlock, failed_answer: str) -> ParsedBlock:
        self.correct_calls += 1
        self.seen_failed.append(failed_answer)
        if self.corrections:
            return self.corrections[min(self.correct_calls - 1, len(self.corrections) - 1)]
        return block


@dataclass
class RecordingListener:
    events: list[RunEvent] = field(default_factory=list)

    def on_event(self, event: RunEvent) -> None:
        self.events.append(event)


@dataclass
class IndexHardcodedReasoning:
    """Mimics real adapters, which self-report attempt_index=0 on every call."""

    answers: list[str]
    solve_calls: int = 0

    def solve(self, image: bytes, question_text: str, options: list[Option]) -> SolveAttempt:
        self.solve_calls += 1
        answer = self.answers[min(self.solve_calls - 1, len(self.answers) - 1)]
        return SolveAttempt(raw_answer=answer, question_text_used=question_text, attempt_index=0)

    def correct(self, image: bytes, block: ParsedBlock, failed_answer: str) -> ParsedBlock:
        return block


def _loop(
    ocr: FakeOCR, reasoning: ScriptedReasoning, cap: int = 2
) -> tuple[RetryLoop, RecordingListener]:
    listener = RecordingListener()
    return RetryLoop(ocr, reasoning, listener, retry_cap=cap), listener


IMG = b"fake-image-bytes"


def test_first_attempt_match_changed_false() -> None:
    ocr, reasoning = FakeOCR(), ScriptedReasoning(answers=["C"])
    loop, _ = _loop(ocr, reasoning)
    result = loop.solve_block(IMG)
    assert result.answer == "C"
    assert result.changed is False
    assert result.unresolved is False
    assert result.attempts == 1


def test_match_after_one_correction_changed_true() -> None:
    ocr, reasoning = FakeOCR(), ScriptedReasoning(answers=["Z", "C"])
    loop, _ = _loop(ocr, reasoning)
    result = loop.solve_block(IMG)
    assert result.answer == "C"
    assert result.changed is True
    assert result.attempts == 2


def test_match_only_at_cap_succeeds_changed_true() -> None:
    ocr, reasoning = FakeOCR(), ScriptedReasoning(answers=["Z", "K", "C"])
    loop, _ = _loop(ocr, reasoning)
    result = loop.solve_block(IMG)
    assert result.answer == "C"
    assert result.changed is True
    assert result.attempts == 3  # cap=2 corrections -> 3 solve attempts


def test_cap_exhausted_returns_unresolved_with_tiered_best_guess() -> None:
    ocr, reasoning = FakeOCR(), ScriptedReasoning(answers=["Z", "K", "Q"])
    loop, _ = _loop(ocr, reasoning)
    result = loop.solve_block(IMG)
    assert result.unresolved is True
    assert result.changed is True
    assert result.attempts == 3


def test_unresolved_fuzzy_tier_rescues_confusable_letter() -> None:
    # "G" is a confusable of C (strict check fails, fuzzy tier rescues).
    ocr, reasoning = FakeOCR(), ScriptedReasoning(answers=["G", "Z", "K"])
    loop, _ = _loop(ocr, reasoning)
    result = loop.solve_block(IMG)
    assert result.unresolved is True
    assert result.answer == "C"


def test_correct_receives_image_current_block_and_failed_answer() -> None:
    ocr, reasoning = FakeOCR(), ScriptedReasoning(answers=["Z", "C"])
    loop, _ = _loop(ocr, reasoning)
    loop.solve_block(IMG)
    assert reasoning.correct_calls == 1
    assert reasoning.seen_images[0] == IMG
    assert reasoning.seen_failed[0] == "Z"


def test_corrected_block_feeds_next_solve() -> None:
    corrected = ParsedBlock(question_text="کدام شهر ایران؟", options=OPTIONS, raw_text=RAW_TEXT)
    ocr, reasoning = FakeOCR(), ScriptedReasoning(answers=["Z", "C"], corrections=[corrected])
    loop, _ = _loop(ocr, reasoning)
    loop.solve_block(IMG)
    assert reasoning.seen_questions[0] == "کدام شهر؟"
    assert reasoning.seen_questions[1] == "کدام شهر ایران؟"


def test_original_ocr_text_is_the_pre_noise_pre_correction_text() -> None:
    ocr, reasoning = FakeOCR(), ScriptedReasoning(answers=["Z", "C"])
    loop, _ = _loop(ocr, reasoning)
    result = loop.solve_block(IMG)
    assert result.original_ocr_text == RAW_TEXT


def test_ocr_runs_exactly_once() -> None:
    ocr, reasoning = FakeOCR(), ScriptedReasoning(answers=["Z", "Z", "C"])
    loop, _ = _loop(ocr, reasoning)
    loop.solve_block(IMG)
    assert ocr.calls == 1


def test_noise_applied_after_parse_when_requested() -> None:
    ocr = FakeOCR()
    injector = NoiseInjector(rate=0.5, seed=3)
    listener = RecordingListener()
    reasoning = ScriptedReasoning(answers=["C"])
    loop = RetryLoop(ocr, reasoning, listener, retry_cap=2, injector=injector)
    result = loop.solve_block(IMG)
    assert result.original_ocr_text == RAW_TEXT  # original survives injection
    assert reasoning.seen_questions[0] != "کدام شهر؟"  # solve saw corrupted text


def test_events_emitted_per_transition() -> None:
    ocr, reasoning = FakeOCR(), ScriptedReasoning(answers=["Z", "C"])
    loop, listener = _loop(ocr, reasoning)
    loop.solve_block(IMG)
    states = [e.run_state for e in listener.events]
    assert states == ["SOLVE", "VERIFY", "CORRECT", "SOLVE", "VERIFY", "DONE"]
    assert listener.events[0].attempt_index == 0
    assert listener.events[3].attempt_index == 1


def test_terminates_against_adversarial_providers() -> None:
    for answers in (["Z"] * 10, ["", " ", "K", "Q", "Z"] * 3):
        ocr, reasoning = FakeOCR(), ScriptedReasoning(answers=answers)
        loop, _ = _loop(ocr, reasoning)
        result = loop.solve_block(IMG)
        assert result.attempts == 3
        assert result.unresolved is True


def test_retry_cap_from_config_not_hardcoded() -> None:
    ocr, reasoning = FakeOCR(), ScriptedReasoning(answers=["Z", "C"])
    loop, _ = _loop(ocr, reasoning, cap=1)
    result = loop.solve_block(IMG)
    assert result.attempts == 2  # cap=1 -> max 2 solve attempts
    ocr2, reasoning2 = FakeOCR(), ScriptedReasoning(answers=["Z", "Z", "Z", "C"])
    loop2, _ = _loop(ocr2, reasoning2, cap=3)
    assert loop2.solve_block(IMG).attempts == 4


class IndexObliviousReasoning(ScriptedReasoning):
    """Mimics real adapters: always reports attempt_index=0 regardless of call count."""

    def solve(self, image: bytes, question_text: str, options: list[Option]) -> SolveAttempt:
        attempt = super().solve(image, question_text, options)
        return SolveAttempt(
            raw_answer=attempt.raw_answer, question_text_used=question_text, attempt_index=0
        )


def test_changed_flag_does_not_depend_on_adapter_reported_index() -> None:
    ocr, reasoning = FakeOCR(), IndexObliviousReasoning(answers=["Z", "C"])
    loop, _ = _loop(ocr, reasoning)
    result = loop.solve_block(IMG)
    assert result.attempts == 2
    assert result.changed is True


def test_done_event_carries_the_final_attempt_index() -> None:
    ocr, reasoning = FakeOCR(), IndexObliviousReasoning(answers=["Z", "C"])
    loop, listener = _loop(ocr, reasoning)
    loop.solve_block(IMG)
    done_events = [e for e in listener.events if e.run_state == "DONE"]
    assert len(done_events) == 1
    assert done_events[0].attempt_index == 1


def test_changed_true_even_when_adapters_hardcode_index_zero() -> None:
    # Regression guard for the E1 fix: real adapters self-report attempt_index=0,
    # so `changed` must derive from the attempt count, never from adapter state.
    ocr, reasoning = FakeOCR(), IndexHardcodedReasoning(answers=["Z", "C"])
    loop, _ = _loop(ocr, reasoning)
    result = loop.solve_block(IMG)
    assert result.attempts == 2
    assert result.changed is True


def test_pre_parsed_ocr_text_skips_ocr_call_but_keeps_the_loop() -> None:
    ocr, reasoning = FakeOCR(), ScriptedReasoning(answers=["Z", "C"])
    loop, listener = _loop(ocr, reasoning)
    result = loop.solve_block(IMG, extracted=OCRText(text=RAW_TEXT, provider="client"))
    assert ocr.calls == 0  # no OCR call
    assert result.answer == "C"
    assert result.changed is True
    assert result.original_ocr_text == RAW_TEXT
    states = [e.run_state for e in listener.events]
    assert states == ["SOLVE", "VERIFY", "CORRECT", "SOLVE", "VERIFY", "DONE"]
