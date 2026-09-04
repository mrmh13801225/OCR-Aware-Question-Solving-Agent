"""Domain models for the OCR-aware question solving loop."""

from dataclasses import dataclass
from typing import Literal

AnswerMapping = Literal["trust_model", "labels_then_position"]
RunState = Literal[
    "SOLVE", "VERIFY", "CORRECT", "DONE", "UNRESOLVED", "PARSE", "TIMEOUT"
]
# Events outside any single solve attempt (PARSE recovery, stream TIMEOUT)
# carry this sentinel instead of a real index.
NON_ATTEMPT_INDEX = -1

# A run ends the moment one of these states is observed; everything else
# is progress the SSE stream keeps following.
TERMINAL_RUN_STATES: frozenset[str] = frozenset({"DONE", "UNRESOLVED"})

# The block's label vocabulary, positionally ordered. The parser assigns
# labels from this sequence; the matcher maps answers back into it.
OPTION_LABELS: tuple[str, ...] = tuple(chr(ord("A") + i) for i in range(8))


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
    """One solve call's outcome, against the question text used for that attempt.

    Carries no attempt index by design: the retry loop counts attempts itself
    (DESIGN.md §5) — an adapter-reported index is never trusted.
    """

    raw_answer: str
    question_text_used: str


@dataclass(frozen=True)
class BlockResult:
    """Final per-block output; shape matches the deliverable JSON plus extras."""

    answer: str
    question_text: str
    changed: bool
    original_ocr_text: str
    unresolved: bool = False
    attempts: int = 1
