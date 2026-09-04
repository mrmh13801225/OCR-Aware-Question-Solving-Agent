"""Shared reasoning-provider prompts: every adapter demands the same contract.

Solve trusts the image over possibly-wrong OCR and answers with only a
letter; correction demands the minimal plausible, image-grounded edit as
JSON with labels and order unchanged. Extracted so the two adapters cannot
drift apart.
"""

_SOLVE_SYSTEM = (
    "You solve Persian multiple-choice questions from a scan image. "
    "The OCR text provided may contain errors; trust the image over the text. "
    "Answer with ONLY the option letter (A, B, C, or D) on its own line."
)

_CORRECT_SYSTEM = (
    "You correct OCR transcription errors in a Persian multiple-choice question, "
    "using the scan image as ground truth. Make the minimal plausible correction: "
    "fix only the characters/words that are wrong, never rewrite the question, "
    "never invent or remove options, never change an option label. "
    "Reply with ONLY a JSON object: "
    '{"question_text": "...", "options": [{"label": "A", "text": "..."}, ...]} '
    "with the same option labels in the same order."
)


def solve_system_prompt() -> str:
    return _SOLVE_SYSTEM


def correct_system_prompt() -> str:
    return _CORRECT_SYSTEM


def solve_user_text(question_text: str, option_lines: str) -> str:
    return (
        f"OCR text (may be wrong):\n{question_text}\n\nOptions:\n{option_lines}\n\n"
        "Which option is correct? Answer with only the letter."
    )


def correct_user_text(question_text: str, option_lines: str, failed_answer: str) -> str:
    return (
        f"The OCR text below produced the answer '{failed_answer}', which matches "
        "none of the options — evidence the text is misread. Correct it minimally.\n\n"
        f"OCR text (may be wrong):\n{question_text}\n\nOptions:\n{option_lines}"
    )


_TRANSCRIBE_SYSTEM = (
    "You transcribe Persian multiple-choice exam scans. Output ONLY a JSON object: "
    '{"question_text": "...", "options": [{"label": "A", "text": "..."}, ...]} '
    "with labels A, B, C, D in reading order. Transcribe exactly what the scan shows; "
    "if an option is math typeset, reproduce it verbatim in the text field."
)

_TRANSCRIBE_USER = "Transcribe this question block from the image."

# The one re-ask: reasoning models occasionally reply conversationally
# instead of with the JSON object the contract demands.
NUDGE_SUFFIX = (
    "\n\nYour previous reply was not a JSON object. "
    "Respond with ONLY the JSON object, nothing else."
)


def with_json_nudge(user_text: str) -> str:
    return user_text + NUDGE_SUFFIX


def options_block(options) -> str:
    """The options rendered one per line as 'A) text' — the wire form."""
    return "\n".join(f"{o.label}) {o.text}" for o in options)


def transcribe_system_prompt() -> str:
    return _TRANSCRIBE_SYSTEM


def transcribe_user_text() -> str:
    return _TRANSCRIBE_USER
