"""T4.3 — run registry and SSE stream behavior."""

from api.run_registry import MAX_EVENTS_PER_RUN, RunEventLog
from core.domain.ports import RunEvent


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
    assert not log.known("nope")


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


def test_stream_endpoint_serves_sse_payloads() -> None:
    import asyncio
    import base64

    from httpx import ASGITransport, AsyncClient

    from api.main import create_app
    from config import Settings

    async def scenario() -> None:
        settings = Settings(_env_file=None, ocr_provider="fake", reasoning_provider="fake")
        app = create_app(results_dir="ignored", settings=settings)
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as http:
            solve = await http.post(
                "/api/v1/blocks/solve",
                json={
                    "image_base64": base64.b64encode(b"fake-png").decode("utf-8"),
                    "run_id": "live-1",
                },
            )
            assert solve.status_code == 200
            stream_response = await http.get("/api/v1/blocks/live-1/stream")
            assert stream_response.status_code == 200
            assert "text/event-stream" in stream_response.headers["content-type"]
            assert "SOLVE" in stream_response.text
            assert "DONE" in stream_response.text
            missing = await http.get("/api/v1/blocks/never-existed/stream")
            assert missing.status_code == 404

    asyncio.run(scenario())
