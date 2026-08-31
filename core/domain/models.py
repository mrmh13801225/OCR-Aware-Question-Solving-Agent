"""Domain models for the OCR-aware question solving loop."""

from dataclasses import dataclass
from typing import Literal

AnswerMapping = Literal["trust_model", "labels_then_position"]
RunState = Literal["SOLVE", "VERIFY", "CORRECT", "DONE", "UNRESOLVED"]


@dataclass(frozen=True)
class Option:
    """One answer choice, label normalized to A/B/C/D."""

    label: str
    text: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "label", self.label.upper())


@dataclass(frozen=True)
class ParsedBlock:
    """A question block parsed out of raw OCR text."""

    question_text: str
    options: list[Option]
    raw_text: str


@dataclass(frozen=True)
class SolveAttempt:
    """One solve call's outcome, against the question text used for that attempt."""

    raw_answer: str
    question_text_used: str
    attempt_index: int


@dataclass(frozen=True)
class BlockResult:
    """Final per-block output; shape matches the deliverable JSON plus extras."""

    answer: str
    question_text: str
    changed: bool
    original_ocr_text: str
    unresolved: bool = False
    attempts: int = 1
