"""T4.2 — blocks/providers/results routes over in-process ASGI, fake providers."""

import base64

import pytest
from httpx import ASGITransport, AsyncClient

from api.main import create_app
from config import Settings
from persistence.json_repository import JSONFileResultRepository

IMAGE_B64 = base64.b64encode(b"fake-png-bytes").decode("utf-8")


@pytest.fixture
async def client(tmp_path):
    settings = Settings(_env_file=None, ocr_provider="fake", reasoning_provider="fake")
    app = create_app(results_dir=tmp_path / "results", settings=settings)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as http:
        yield http


async def test_health_ok(client) -> None:
    response = await client.get("/api/v1/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


async def test_providers_lists_registered_with_status(client) -> None:
    response = await client.get("/api/v1/providers")
    body = response.json()
    assert response.status_code == 200
    assert set(body["ocr"]) >= {"nanonets", "datalab", "local_vlm", "fake"}
    assert set(body["reasoning"]) >= {"claude", "openai_compatible", "fake"}
    assert body["configured"]["ocr"] and body["configured"]["reasoning"]


async def test_solve_returns_required_schema_fields(client) -> None:
    response = await client.post("/api/v1/blocks/solve", json={"image_base64": IMAGE_B64})
    assert response.status_code == 200
    body = response.json()
    for field in (
        "answer",
        "question_text",
        "changed",
        "original_ocr_text",
        "unresolved",
        "attempts",
    ):
        assert field in body
    assert body["answer"] == "A"  # fake reasoning provider picks option 1
    assert body["changed"] is False


async def test_solve_accepts_ocr_text_override(client) -> None:
    ocr_text = "سؤال تستی؟\n۱) الف\n۲) ب\n۳) ج\n۴) د"
    response = await client.post(
        "/api/v1/blocks/solve", json={"image_base64": IMAGE_B64, "ocr_text": ocr_text}
    )
    body = response.json()
    assert body["original_ocr_text"] == ocr_text


async def test_solve_with_inject_noise_produces_changed_flow(client) -> None:
    response = await client.post(
        "/api/v1/blocks/solve", json={"image_base64": IMAGE_B64, "inject_noise": True}
    )
    assert response.status_code == 200
    body = response.json()
    assert body["original_ocr_text"] != body["question_text"]  # noise altered the parsed text


async def test_solve_provider_overrides_respected(client) -> None:
    response = await client.post(
        "/api/v1/blocks/solve",
        json={"image_base64": IMAGE_B64, "ocr_provider": "fake", "reasoning_provider": "fake"},
    )
    assert response.status_code == 200


async def test_solve_with_run_id_registers_events_in_registry(client) -> None:
    response = await client.post(
        "/api/v1/blocks/solve", json={"image_base64": IMAGE_B64, "run_id": "run-42"}
    )
    assert response.status_code == 200
    registry = client._transport.app.state.run_registry  # type: ignore[attr-defined]
    assert len(registry.events("run-42")) >= 2  # SOLVE + VERIFY + DONE at minimum


async def test_batch_solves_each_block_and_returns_list(client) -> None:
    response = await client.post(
        "/api/v1/blocks/batch",
        json={"blocks": [{"image_base64": IMAGE_B64}, {"image_base64": IMAGE_B64}]},
    )
    assert response.status_code == 200
    body = response.json()
    assert isinstance(body["results"], list) and len(body["results"]) == 2
    assert all("answer" in result for result in body["results"])


async def test_results_endpoint_lists_saved_results(client) -> None:
    await client.post("/api/v1/blocks/solve", json={"image_base64": IMAGE_B64})
    response = await client.get("/api/v1/results")
    assert response.status_code == 200
    body = response.json()
    assert len(body["results"]) == 1


async def test_result_persisted_to_json_repository(client, tmp_path) -> None:
    await client.post("/api/v1/blocks/solve", json={"image_base64": IMAGE_B64})
    repo = JSONFileResultRepository(results_dir=tmp_path / "results")
    assert len(repo.list()) == 1
