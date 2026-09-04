"""Env-driven settings and the provider factory/registry — the one wiring point."""

import logging
from collections.abc import Callable
from typing import Literal, get_args

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

from core.domain.models import AnswerMapping, Option, ParsedBlock, SolveAttempt, SolveMode
from core.domain.ports import OCRProvider, OCRText, ReasoningProvider
from providers.ocr.datalab import DatalabOCRProvider
from providers.ocr.local_vlm import LocalVLMOCRProvider
from providers.ocr.nanonets import NanonetsOCRProvider
from providers.reasoning.claude import ClaudeReasoningProvider
from providers.reasoning.openai_compatible import OpenAICompatibleReasoningProvider

VALID_OCR = Literal["nanonets", "datalab", "local_vlm", "fake"]
VALID_REASONING = Literal["claude", "openai_compatible", "fake"]
VALID_LOG_LEVELS = Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]

OCR_PROVIDER_NAMES = get_args(VALID_OCR)
REASONING_PROVIDER_NAMES = get_args(VALID_REASONING)
ANSWER_MAPPINGS = get_args(AnswerMapping)
SOLVE_MODES = get_args(SolveMode)

# Image formats every HTTP client of this app accepts from users (CLI batch,
# run_samples, the web dropzone's accept attribute).
IMAGE_SUFFIXES: frozenset[str] = frozenset({".png", ".jpg", ".jpeg", ".webp"})

# The deterministic stand-ins answer with this "model" name; surfaced by the
# providers route so the UI selector shows something for them.
FAKE_MODEL_NAME = "fake"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    ocr_provider: VALID_OCR = "nanonets"
    reasoning_provider: VALID_REASONING = "claude"

    nanonets_api_key: str = ""
    datalab_api_key: str = ""
    local_vlm_base_url: str = "http://localhost:8000/v1"
    local_vlm_model: str = "qwen2.5-vl-7b-instruct"
    local_vlm_api_key: str = ""  # only for gated local servers (vLLM --api-key, LM Studio)

    anthropic_api_key: str = ""
    openai_compat_base_url: str = ""
    openai_compat_api_key: str = ""
    openai_compat_model: str = ""

    retry_cap: int = Field(default=2, ge=0)
    answer_mapping: AnswerMapping = "trust_model"
    solve_mode: SolveMode = "image_grounded"
    noise_rate: float = Field(default=0.05, ge=0.0, le=1.0)
    noise_seed: int = 42
    results_dir: str = "./results"

    # The solve loop's audit trail (original OCR, prompts, responses,
    # corrections) logs at INFO; raising LOG_LEVEL to WARNING quiets it.
    log_level: VALID_LOG_LEVELS = "INFO"
    log_file: str = ""  # optional: append the same trail to this file


def configure_logging(level: str, log_file: str = "") -> None:
    logging.basicConfig(
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
        level=level,
        filename=log_file or None,
        force=True,  # reconfigure even if something (pytest, uvicorn) already set a handler
    )


class FakeOCRProvider:
    """Deterministic no-network stand-in; registered under the 'fake' name."""

    def extract_text(self, image: bytes) -> OCRText:
        return OCRText(
            text="کدام گزینه درست است؟\n1) گزینه یک\n2) گزینه دو\n3) گزینه سه\n4) گزینه چهار",
            provider="fake",
        )


class FakeReasoningProvider:
    """Always answers with the first option's label, deterministically."""

    def solve(self, image: bytes, question_text: str, options: list[Option]) -> SolveAttempt:
        answer = options[0].label if options else "A"
        return SolveAttempt(raw_answer=answer, question_text_used=question_text)

    def correct(self, image: bytes, block: ParsedBlock, failed_answer: str) -> ParsedBlock:
        return block

    def transcribe(self, image: bytes) -> ParsedBlock:
        # deliberately unparseable: a fake transcription forces the loop's
        # recovery path to exhaust, exercising the unresolved outcome
        return ParsedBlock(question_text="", options=[], raw_text="")


OCR_PROVIDER_REGISTRY: dict[str, Callable[[Settings], OCRProvider]] = {
    "datalab": lambda settings: DatalabOCRProvider(api_key=settings.datalab_api_key),
    "fake": lambda _settings: FakeOCRProvider(),
    "local_vlm": lambda settings: LocalVLMOCRProvider(
        base_url=settings.local_vlm_base_url,
        model=settings.local_vlm_model,
        api_key=settings.local_vlm_api_key,
    ),
    "nanonets": lambda settings: NanonetsOCRProvider(api_key=settings.nanonets_api_key),
}

REASONING_PROVIDER_REGISTRY: dict[str, Callable[[Settings, SolveMode], ReasoningProvider]] = {
    "claude": lambda settings, solve_mode: ClaudeReasoningProvider(
        api_key=settings.anthropic_api_key, solve_mode=solve_mode
    ),
    "fake": lambda _settings, _solve_mode: FakeReasoningProvider(),
    "openai_compatible": lambda settings, solve_mode: OpenAICompatibleReasoningProvider(
        base_url=settings.openai_compat_base_url,
        api_key=settings.openai_compat_api_key,
        model=settings.openai_compat_model,
        solve_mode=solve_mode,
    ),
}


def _valid_names_error(kind: str, name: str, valid: tuple[str, ...]) -> ValueError:
    return ValueError(f"Unknown {kind} provider '{name}'. Valid options: {', '.join(valid)}.")


def build_ocr_provider(name: str, settings: Settings) -> OCRProvider:
    builder = OCR_PROVIDER_REGISTRY.get(name)
    if builder is None:
        raise _valid_names_error("OCR", name, tuple(OCR_PROVIDER_REGISTRY))
    return builder(settings)


def build_reasoning_provider(
    name: str, settings: Settings, solve_mode: SolveMode | None = None
) -> ReasoningProvider:
    builder = REASONING_PROVIDER_REGISTRY.get(name)
    if builder is None:
        raise _valid_names_error("reasoning", name, tuple(REASONING_PROVIDER_REGISTRY))
    return builder(settings, settings.solve_mode if solve_mode is None else solve_mode)
