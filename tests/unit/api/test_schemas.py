"""T4.1 — API schemas mirror API_SPEC.md exactly."""

import pytest
from pydantic import ValidationError

from api.schemas import BlockResultResponse, SolveRequest


def test_solve_request_defaults() -> None:
    request = SolveRequest(image_base64="abc")
    assert request.image_base64 == "abc"
    assert request.run_id is None
    assert request.ocr_text is None
    assert request.ocr_provider is None
    assert request.reasoning_provider is None
    assert request.answer_mapping is None
    assert request.inject_noise is False


def test_solve_request_accepts_all_documented_fields() -> None:
    request = SolveRequest(
        image_base64="abc",
        run_id="run-1",
        ocr_text="already extracted",
        ocr_provider="datalab",
        reasoning_provider="openai_compatible",
        answer_mapping="labels_then_position",
        inject_noise=True,
    )
    assert request.run_id == "run-1"
    assert request.inject_noise is True


def test_solve_request_rejects_unknown_answer_mapping() -> None:
    with pytest.raises(ValidationError):
        SolveRequest(image_base64="abc", answer_mapping="wat")


def test_solve_request_rejects_unknown_solve_mode() -> None:
    with pytest.raises(ValidationError):
        SolveRequest(image_base64="abc", solve_mode="wat")


def test_solve_request_solve_mode_defaults_to_none() -> None:
    request = SolveRequest(image_base64="abc")
    assert request.solve_mode is None  # omission falls back to the server's setting


def test_solve_response_matches_brief_schema_fields() -> None:
    response = BlockResultResponse(
        answer="C", question_text="q", changed=True, original_ocr_text="o"
    )
    assert response.unresolved is False
    assert response.attempts == 1
    payload = response.model_dump()
    for field in ("answer", "question_text", "changed", "original_ocr_text"):
        assert field in payload


def test_solve_response_includes_attempts_changed_unresolved() -> None:
    response = BlockResultResponse(
        answer="B", question_text="q", changed=False, original_ocr_text="o", attempts=3
    )
    assert response.attempts == 3
    assert response.changed is False
    assert response.unresolved is False
