"""Pydantic DTOs mirroring API_SPEC.md — the API's only public vocabulary."""

from pydantic import BaseModel, Field

from config import VALID_OCR, VALID_REASONING
from core.domain.models import AnswerMapping, BlockResult


class SolveRequest(BaseModel):
    image_base64: str
    run_id: str | None = None
    ocr_text: str | None = None
    ocr_provider: VALID_OCR | None = None
    reasoning_provider: VALID_REASONING | None = None
    answer_mapping: AnswerMapping | None = None
    inject_noise: bool = False


class BlockResultResponse(BaseModel):
    answer: str
    question_text: str
    changed: bool
    original_ocr_text: str
    unresolved: bool = False
    attempts: int = Field(default=1, ge=0)

    @classmethod
    def from_domain(cls, result: BlockResult) -> "BlockResultResponse":
        return cls(**vars(result))


class BatchRequest(BaseModel):
    blocks: list[SolveRequest]
