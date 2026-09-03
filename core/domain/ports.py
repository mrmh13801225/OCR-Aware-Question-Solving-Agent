"""Outbound ports: the seams core talks through; adapters plug in from the outside."""

from dataclasses import dataclass
from typing import Protocol, runtime_checkable

from core.domain.models import BlockResult, Option, ParsedBlock, RunState, SolveAttempt


@dataclass(frozen=True)
class OCRText:
    """Raw text extracted from one image."""

    text: str
    provider: str


@runtime_checkable
class OCRProvider(Protocol):
    """Step zero: turn image bytes into raw text."""

    def extract_text(self, image: bytes) -> OCRText: ...


@runtime_checkable
class ReasoningProvider(Protocol):
    """Vision-capable solver; correct() re-reads the image, per the brief."""

    def solve(self, image: bytes, question_text: str, options: list[Option]) -> SolveAttempt: ...

    def correct(self, image: bytes, block: ParsedBlock, failed_answer: str) -> ParsedBlock: ...

    def transcribe(self, image: bytes) -> ParsedBlock:
        """Re-read the image and return a parseable block; used when OCR text
        is so broken the parser rejects it outright."""
        ...


class ResultRepository(Protocol):
    """Flat-JSON persistence of per-block results."""

    def save(self, result: BlockResult) -> None: ...

    def list(self) -> list[BlockResult]: ...


@dataclass(frozen=True)
class RunEvent:
    """One progress event emitted per state transition of the retry loop."""

    run_state: RunState
    attempt_index: int
    detail: str


@runtime_checkable
class RunEventListener(Protocol):
    """Observer port: one event stream feeds SSE, the CLI trace, and tests."""

    def on_event(self, event: RunEvent) -> None: ...
