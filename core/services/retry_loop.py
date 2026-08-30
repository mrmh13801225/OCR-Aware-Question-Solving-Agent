"""The retry loop: OCR -> parse -> (inject) -> solve/match/correct up to the cap."""

from dataclasses import dataclass

from core.domain.errors import ParseError
from core.domain.models import BlockResult, ParsedBlock, SolveAttempt
from core.domain.ports import OCRProvider, ReasoningProvider, RunEvent, RunEventListener
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
    answer_mapping: str = "trust_model"

    def solve_block(self, image: bytes) -> BlockResult:
        extracted = self.ocr.extract_text(image)
        original_ocr_text = extracted.text
        block = parse(original_ocr_text)

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

    def _done(
        self, attempt: SolveAttempt, block: ParsedBlock, count: int, original_ocr_text: str
    ) -> BlockResult:
        answer = resolve_letter(self.answer_mapping, attempt.raw_answer, block.options)
        if answer is None:  # mapped but not to this block's options; treat as unresolved
            return self._unresolved([attempt], block, original_ocr_text)
        self._emit("DONE", attempt.attempt_index, answer)
        return BlockResult(
            answer=answer,
            question_text=block.question_text,
            changed=attempt.attempt_index > 0,
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

    def _emit(self, state: str, attempt_index: int, detail: str) -> None:
        event = RunEvent(run_state=state, attempt_index=attempt_index, detail=detail)
        self.listener.on_event(event)


__all__ = ["RetryLoop", "ParseError"]
