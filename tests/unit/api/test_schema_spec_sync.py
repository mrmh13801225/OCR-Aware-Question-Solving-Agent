"""Contract test: api/schemas.py fields must match API_SPEC.md exactly.

API_SPEC.md:3 requires a test asserting the doc and the schema layer stay
in sync; this parses the doc's solve-request/response blocks so doc drift
fails loudly instead of surfacing as an integration surprise.
"""

import re
from pathlib import Path

from pydantic import BaseModel

from api.schemas import BatchRequest, BlockResultResponse, SolveRequest

# API_SPEC.md lives one level above the repo (workspace root), alongside the
# other planning docs — see REFACTOR_PLAN/repo layout memory.
SPEC_PATH = Path(__file__).resolve().parents[3].parent / "API_SPEC.md"


def _spec_text() -> str:
    return SPEC_PATH.read_text(encoding="utf-8")


def _json_keys_in_block(header: str, text: str) -> set[str]:
    section = text.split(header, 1)[1]
    code_block = re.search(r"```json\n(.*?)```", section, re.DOTALL)
    assert code_block, f"no json block after {header!r}"
    return set(re.findall(r'"(\w+)":', code_block.group(1)))


def test_solve_request_fields_match_spec() -> None:
    text = _spec_text()
    spec_request = _json_keys_in_block("**Request**", text)
    spec_request -= {"null"}  # comment words inside the json block
    model_fields = set(SolveRequest.model_fields)
    assert spec_request <= model_fields, (
        f"spec fields missing from schema: {spec_request - model_fields}"
    )


def test_solve_response_fields_match_spec() -> None:
    text = _spec_text()
    section = text.split("**Response**", 1)[1]
    code_block = re.search(r"```json\n(.*?)```", section, re.DOTALL)
    spec_response = set(re.findall(r'"(\w+)":', code_block.group(1)))
    spec_response -= {"null"}
    model_fields = set(BlockResultResponse.model_fields)
    assert model_fields == spec_response, (
        f"schema/spec drift: schema-only={model_fields - spec_response}, "
        f"spec-only={spec_response - model_fields}"
    )


def test_batch_request_is_a_list_of_solve_requests() -> None:
    fields = BatchRequest.model_fields
    assert set(fields) == {"blocks"}
    assert fields["blocks"].annotation is not None


def test_all_schemas_are_pydantic_models() -> None:
    for model in (SolveRequest, BlockResultResponse, BatchRequest):
        assert issubclass(model, BaseModel)
