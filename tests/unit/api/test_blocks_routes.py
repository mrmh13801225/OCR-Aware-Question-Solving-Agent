"""T4.2 — blocks/providers/results routes over in-process ASGI, fake providers."""

import base64

import pytest
from httpx import ASGITransport, AsyncClient

from api.main import create_app
from config import Settings
from core.domain.models import ParsedBlock
from persistence.json_repository import JSONFileResultRepository

IMAGE_B64 = base64.b64encode(b"fake-png-bytes").decode("utf-8")


@pytest.fixture
async def client(tmp_path):
    settings = Settings(
        _env_file=None,
        ocr_provider="fake",
        reasoning_provider="fake",
        results_dir=str(tmp_path / "results"),
    )
    app = create_app(settings=settings)
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


async def test_solve_unknown_provider_name_returns_422(client) -> None:
    """A misspelled provider name is a client error — pydantic validates the
    Literal, so it must 422, not surface as an unhandled 500 from the factory."""
    response = await client.post(
        "/api/v1/blocks/solve",
        json={"image_base64": IMAGE_B64, "ocr_provider": "nope"},
    )
    assert response.status_code == 422


async def test_solve_unknown_reasoning_provider_name_returns_422(client) -> None:
    response = await client.post(
        "/api/v1/blocks/solve",
        json={"image_base64": IMAGE_B64, "reasoning_provider": "nope"},
    )
    assert response.status_code == 422


async def test_solve_unknown_solve_mode_returns_422(client) -> None:
    response = await client.post(
        "/api/v1/blocks/solve",
        json={"image_base64": IMAGE_B64, "solve_mode": "nope"},
    )
    assert response.status_code == 422


async def test_solve_mode_override_reaches_the_factory(client, monkeypatch) -> None:
    """The per-request solve_mode must select the mode the factory builds
    with — a capturing fake at the registry seam makes it observable."""
    from core.domain.models import SolveAttempt

    captured_modes: list[str] = []

    def recording_fake(settings, solve_mode):
        captured_modes.append(solve_mode)

        class RecordingReasoning:
            def solve(self, image: bytes, question_text: str, options):
                return SolveAttempt(raw_answer=options[0].label, question_text_used=question_text)

            def correct(self, image: bytes, block, failed_answer: str):
                return block

            def transcribe(self, image: bytes):
                return ParsedBlock(question_text="", options=[], raw_text="")

        return RecordingReasoning()

    import config

    monkeypatch.setitem(config.REASONING_PROVIDER_REGISTRY, "fake", recording_fake)
    await client.post(
        "/api/v1/blocks/solve",
        json={"image_base64": IMAGE_B64, "solve_mode": "text_only"},
    )
    assert captured_modes == ["text_only"]


async def test_solve_mode_omitted_falls_back_to_settings(client, monkeypatch) -> None:
    from core.domain.models import ParsedBlock, SolveAttempt

    captured_modes: list[str] = []

    def recording_fake(settings, solve_mode):
        captured_modes.append(solve_mode)

        class RecordingReasoning:
            def solve(self, image: bytes, question_text: str, options):
                return SolveAttempt(raw_answer=options[0].label, question_text_used=question_text)

            def correct(self, image: bytes, block, failed_answer: str):
                return block

            def transcribe(self, image: bytes):
                return ParsedBlock(question_text="", options=[], raw_text="")

        return RecordingReasoning()

    import config

    monkeypatch.setitem(config.REASONING_PROVIDER_REGISTRY, "fake", recording_fake)
    settings_with_mode = Settings(
        _env_file=None, ocr_provider="fake", reasoning_provider="fake", solve_mode="text_only"
    )
    app = create_app(settings=settings_with_mode)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as http:
        await http.post("/api/v1/blocks/solve", json={"image_base64": IMAGE_B64})
    assert captured_modes == ["text_only"]  # from the setting, not the request


async def test_solve_provider_overrides_respected(client, monkeypatch) -> None:
    """The override must actually select the named provider from the factory
    seam — a 200 alone proves nothing."""
    from core.domain.errors import ProviderTimeoutError

    class ExplodingReasoning:
        def __init__(self, *args, **kwargs) -> None: ...

        def solve(self, image: bytes, question_text: str, options):
            raise ProviderTimeoutError("override reached the factory", provider="fake")

        def correct(self, image: bytes, block, failed_answer: str): ...
        def transcribe(self, image: bytes): ...

    monkeypatch.setitem(
        __import__("config").REASONING_PROVIDER_REGISTRY, "fake", ExplodingReasoning
    )
    response = await client.post(
        "/api/v1/blocks/solve",
        json={"image_base64": IMAGE_B64, "reasoning_provider": "fake"},
    )
    assert response.status_code == 502
    assert "override reached the factory" in response.text


async def test_solve_with_run_id_registers_events_in_registry(client) -> None:
    response = await client.post(
        "/api/v1/blocks/solve", json={"image_base64": IMAGE_B64, "run_id": "run-42"}
    )
    assert response.status_code == 200
    registry = client._transport.app.state.run_registry
    assert [e.run_state for e in registry.events("run-42")] == ["SOLVE", "VERIFY", "DONE"]


async def test_batch_solves_each_block_and_returns_list(client) -> None:
    response = await client.post(
        "/api/v1/blocks/batch",
        json={"blocks": [{"image_base64": IMAGE_B64}, {"image_base64": IMAGE_B64}]},
    )
    assert response.status_code == 200
    body = response.json()
    assert isinstance(body["results"], list) and len(body["results"]) == 2
    assert all("answer" in result for result in body["results"])


async def test_batch_rejects_malformed_blocks_with_422(client) -> None:
    response = await client.post(
        "/api/v1/blocks/batch",
        json={"blocks": [{"image_base64": IMAGE_B64}, {"bogus": 1}]},
    )
    assert response.status_code == 422


async def test_batch_rejects_body_without_blocks_list_with_422(client) -> None:
    response = await client.post("/api/v1/blocks/batch", json={"wrong": []})
    assert response.status_code == 422


async def test_solve_rejects_invalid_base64_with_422(client) -> None:
    response = await client.post("/api/v1/blocks/solve", json={"image_base64": "not-base64!!"})
    assert response.status_code == 422


async def test_providers_lists_models_per_provider(client) -> None:
    response = await client.get("/api/v1/providers")
    body = response.json()
    assert response.status_code == 200
    assert body["models"]["claude"]
    assert body["models"]["local_vlm"]


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


async def test_unparseable_ocr_text_returns_honest_unresolved_result(client) -> None:
    """OCR text the parser rejects outright yields an unresolved result with a
    truthful attempt count — zero solves ran — and no fabricated 'changed'."""
    response = await client.post(
        "/api/v1/blocks/solve",
        json={"image_base64": IMAGE_B64, "ocr_text": "garbage without any options"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["unresolved"] is True
    assert body["attempts"] == 0
    assert body["changed"] is False


async def test_provider_errors_become_502_not_500(client, monkeypatch) -> None:
    """A vendor failure inside the loop must surface as a clean 502 with the
    provider error's message, never an unhandled 500 — exercised at the
    registry seam, not by swapping an internal collaborator."""
    from core.domain.errors import ProviderTimeoutError

    class ExplodingReasoning:
        def __init__(self, *args, **kwargs) -> None: ...

        def solve(self, image: bytes, question_text: str, options):
            raise ProviderTimeoutError("timed out", provider="openai_compatible")

        def correct(self, image: bytes, block, failed_answer: str): ...
        def transcribe(self, image: bytes): ...

    monkeypatch.setitem(
        __import__("config").REASONING_PROVIDER_REGISTRY, "fake", ExplodingReasoning
    )
    response = await client.post("/api/v1/blocks/solve", json={"image_base64": IMAGE_B64})
    assert response.status_code == 502
    assert "timed out" in response.text
    assert "openai_compatible" in response.text


async def test_our_side_errors_are_500_not_502(client, monkeypatch) -> None:
    """ParseError/NoiseError are our bugs, not upstream failures — they must
    not masquerade as a bad gateway."""
    from core.domain.errors import NoiseError

    class ExplodingInjector:
        def __init__(self, *args, **kwargs) -> None: ...

        def corrupt(self, block):
            raise NoiseError("boom")

    monkeypatch.setattr("api.routes.blocks.NoiseInjector", ExplodingInjector)
    # ASGITransport re-raises unhandled app errors by default; a real server
    # converts them to a 500 response, which is the behavior under test.
    transport = ASGITransport(app=client._transport.app, raise_app_exceptions=False)
    async with AsyncClient(transport=transport, base_url="http://test") as http:
        response = await http.post(
            "/api/v1/blocks/solve", json={"image_base64": IMAGE_B64, "inject_noise": True}
        )
    assert response.status_code == 500


async def test_results_dir_setting_controls_persistence(client, tmp_path) -> None:
    """API_SPEC: GET /results reads RESULTS_DIR — the setting must actually
    decide where results land."""
    custom_dir = tmp_path / "custom-results"
    settings = Settings(
        _env_file=None,
        ocr_provider="fake",
        reasoning_provider="fake",
        results_dir=str(custom_dir),
    )
    app = create_app(settings=settings)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as http:
        await http.post("/api/v1/blocks/solve", json={"image_base64": IMAGE_B64})
    assert len(list(custom_dir.glob("*.json"))) == 1
