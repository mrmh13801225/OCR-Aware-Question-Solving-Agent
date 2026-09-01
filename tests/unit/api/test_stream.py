"""T4.3 — run registry and SSE stream behavior."""

import asyncio
import base64

from httpx import ASGITransport, AsyncClient

from api.main import create_app
from api.run_registry import MAX_EVENTS_PER_RUN, RunEventLog
from config import Settings
from core.domain.ports import RunEvent

IMAGE_B64 = base64.b64encode(b"fake-png").decode("utf-8")


def _event(state: str, index: int = 0) -> RunEvent:
    return RunEvent(run_state=state, attempt_index=index, detail="d")


def test_registry_buffers_events_and_replays() -> None:
    log = RunEventLog()
    log.on_event(_event("SOLVE"), run_id="r1")
    log.on_event(_event("VERIFY"), run_id="r1")
    assert [e.run_state for e in log.events("r1")] == ["SOLVE", "VERIFY"]
    assert [e.run_state for e in log.stream_from("r1")] == ["SOLVE", "VERIFY"]


def test_stream_from_after_skips_replayed_prefix() -> None:
    log = RunEventLog()
    for state in ("SOLVE", "VERIFY", "DONE"):
        log.on_event(_event(state), run_id="r1")
    assert [e.run_state for e in log.stream_from("r1", after=1)] == ["VERIFY", "DONE"]


def test_unknown_run_id_is_ignorable() -> None:
    log = RunEventLog()
    assert log.events("nope") == []
    assert log.stream_from("nope") is not None
    assert not log.is_finished("nope")


def test_terminal_event_marks_run_finished() -> None:
    log = RunEventLog()
    log.on_event(_event("SOLVE"), run_id="r1")
    assert not log.is_finished("r1")
    log.on_event(_event("DONE"), run_id="r1")
    assert log.is_finished("r1")


def test_registry_bounded_per_run() -> None:
    log = RunEventLog()
    for i in range(MAX_EVENTS_PER_RUN + 50):
        log.on_event(_event("SOLVE", index=i), run_id="r1")
    assert len(log.events("r1")) == MAX_EVENTS_PER_RUN


def test_events_without_run_id_are_dropped() -> None:
    log = RunEventLog()
    log.on_event(_event("SOLVE"))  # no run_id: no-op (loop used without a run)
    assert log.events("") == []


def test_stream_serves_events_for_stream_first_flow(tmp_path) -> None:
    """API_SPEC sequence: open the stream FIRST, then issue the solve."""

    async def scenario() -> None:
        settings = Settings(_env_file=None, ocr_provider="fake", reasoning_provider="fake")
        app = create_app(results_dir=str(tmp_path / "results"), settings=settings)
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as http:
            # The stream GET runs as a concurrent task; the route yields every
            # 0.1s, so the solve POST interleaves and feeds it events.
            stream_task = asyncio.create_task(http.get("/api/v1/blocks/live-1/stream"))
            await asyncio.sleep(0.3)
            solve = await http.post(
                "/api/v1/blocks/solve",
                json={"image_base64": IMAGE_B64, "run_id": "live-1"},
            )
            assert solve.status_code == 200
            stream_response = await stream_task
            assert stream_response.status_code == 200
            assert "text/event-stream" in stream_response.headers["content-type"]
            assert "SOLVE" in stream_response.text
            assert "DONE" in stream_response.text

    asyncio.run(scenario())


def test_stream_follows_and_terminates_after_solve(tmp_path) -> None:
    """Solve-then-stream (late subscriber): buffered events replay, then close."""

    async def scenario() -> None:
        settings = Settings(_env_file=None, ocr_provider="fake", reasoning_provider="fake")
        app = create_app(results_dir=str(tmp_path / "results"), settings=settings)
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as http:
            solve = await http.post(
                "/api/v1/blocks/solve",
                json={"image_base64": IMAGE_B64, "run_id": "late-1"},
            )
            assert solve.status_code == 200
            stream_response = await http.get("/api/v1/blocks/late-1/stream")
            assert stream_response.status_code == 200
            assert "SOLVE" in stream_response.text
            assert "DONE" in stream_response.text

    asyncio.run(scenario())


def test_ocr_text_override_with_run_id_emits_events(tmp_path) -> None:
    """The pre-parsed path runs the SAME loop — events must flow for SSE."""

    async def scenario() -> None:
        settings = Settings(_env_file=None, ocr_provider="fake", reasoning_provider="fake")
        app = create_app(results_dir=str(tmp_path / "results"), settings=settings)
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as http:
            solve = await http.post(
                "/api/v1/blocks/solve",
                json={
                    "image_base64": IMAGE_B64,
                    "run_id": "override-1",
                    "ocr_text": "کدام شهر؟\n۱) تهران\n۲) مشهد\n۳) اصفهان\n۴) تبریز",
                },
            )
            assert solve.status_code == 200
            registry = app.state.run_registry
            states = [e.run_state for e in registry.events("override-1")]
            assert "SOLVE" in states
            assert "DONE" in states

    asyncio.run(scenario())


def test_stream_ends_with_timeout_event_on_idle_exit(tmp_path) -> None:
    """A stream whose run never produces events closes with a TIMEOUT marker."""

    async def scenario() -> None:
        settings = Settings(_env_file=None, ocr_provider="fake", reasoning_provider="fake")
        app = create_app(results_dir=str(tmp_path / "results"), settings=settings)
        app.state.stream_idle_timeout = 0.2  # fast test; production default 60
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as http:
            stream_response = await http.get("/api/v1/blocks/never-arrives/stream")
            assert stream_response.status_code == 200
            assert "TIMEOUT" in stream_response.text

    asyncio.run(scenario())
