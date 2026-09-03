"""The retry loop: OCR -> parse -> (inject) -> solve/match/correct up to the cap."""

from dataclasses import dataclass

from core.domain.errors import ParseError
from core.domain.models import AnswerMapping, BlockResult, ParsedBlock, RunState, SolveAttempt
from core.domain.ports import (
    OCRProvider,
    OCRText,
    ReasoningProvider,
    RunEvent,
    RunEventListener,
)
from core.services.answer_matcher import matches, resolve_letter
from core.services.best_guess import pick_best
from core.services.block_parser import parse
from core.services.noise_injector import NoiseInjector


@dataclass(frozen=True)
class RetryLoop:
    """State machine per block: SOLVE -> VERIFY -> CORRECT -> DONE/UNRESOLVED.

    The strict match check is the error detector: a mismatch is evidence the
    OCR text is broken, which is what authorizes a correction pass. Cap
    defaults to 2 corrections (3 solve attempts); events are emitted for
    every transition so observers (SSE, CLI trace, tests) see the run live.
    """

    ocr: OCRProvider
    reasoning: ReasoningProvider
    listener: RunEventListener
    retry_cap: int = 2
    injector: NoiseInjector | None = None
    answer_mapping: AnswerMapping = "trust_model"

    def solve_block(self, image: bytes, extracted: OCRText | None = None) -> BlockResult:
        if extracted is None:
            extracted = self.ocr.extract_text(image)
        original_ocr_text = extracted.text

        try:
            block = parse(original_ocr_text)
        except ParseError:
            recovered = self._recover_unparseable_ocr(image)
            if recovered is None:
                self._emit("UNRESOLVED", self.retry_cap, "no parseable transcription")
                return BlockResult(
                    answer="",
                    question_text=original_ocr_text,
                    changed=True,
                    original_ocr_text=original_ocr_text,
                    unresolved=True,
                    attempts=self.retry_cap + 1,
                )
            block = recovered

        if self.injector is not None:
            block = self.injector.corrupt(block)

        attempts: list[SolveAttempt] = []
        for attempt_index in range(self.retry_cap + 1):
            self._emit("SOLVE", attempt_index, block.question_text)
            attempt = self.reasoning.solve(image, block.question_text, block.options)
            attempts.append(attempt)

            self._emit("VERIFY", attempt_index, attempt.raw_answer)
            if matches(attempt.raw_answer, block.options):
                return self._done(attempt, block, len(attempts), original_ocr_text)

            if attempt_index < self.retry_cap:
                self._emit("CORRECT", attempt_index, attempt.raw_answer)
                block = self.reasoning.correct(image, block, attempt.raw_answer)

        return self._unresolved(attempts, block, original_ocr_text)

    def _recover_unparseable_ocr(self, image: bytes) -> ParsedBlock | None:
        """The brief's re-read-the-image remedy, applied to total parse failure:
        the OCR text could not be split into a question and options at all, so
        ask the vision model to transcribe the block from the image. If every
        transcription still fails to parse, return None — the caller surfaces
        an unresolved result rather than a crash.
        """
        for attempts in range(self.retry_cap + 1):
            self._emit("PARSE", attempts, "ocr text unparseable; re-reading the image")
            block = self.reasoning.transcribe(image)
            try:
                return parse(block.raw_text)
            except ParseError:
                continue
        return None

    def _done(
        self, attempt: SolveAttempt, block: ParsedBlock, count: int, original_ocr_text: str
    ) -> BlockResult:
        answer = resolve_letter(self.answer_mapping, attempt.raw_answer, block.options)
        if answer is None:
            raise ValueError(f"matched answer {attempt.raw_answer!r} resolved to no letter")
        self._emit("DONE", count - 1, answer)
        return BlockResult(
            answer=answer,
            question_text=block.question_text,
            changed=count > 1,
            original_ocr_text=original_ocr_text,
            unresolved=False,
            attempts=count,
        )

    def _unresolved(
        self, attempts: list[SolveAttempt], block: ParsedBlock, original_ocr_text: str
    ) -> BlockResult:
        answer = pick_best(attempts, block.options)
        self._emit("UNRESOLVED", len(attempts) - 1, answer)
        return BlockResult(
            answer=answer,
            question_text=block.question_text,
            changed=len(attempts) > 1,
            original_ocr_text=original_ocr_text,
            unresolved=True,
            attempts=len(attempts),
        )

    def _emit(self, state: RunState, attempt_index: int, detail: str) -> None:
        event = RunEvent(run_state=state, attempt_index=attempt_index, detail=detail)
        self.listener.on_event(event)
