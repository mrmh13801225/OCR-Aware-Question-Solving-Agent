"""Shared fixtures for CLI-layer tests: an ephemeral fake-provider API server."""

import threading
import time
from collections.abc import Generator
from pathlib import Path

import pytest
import uvicorn
from fastapi import FastAPI, Request

from api.main import create_app
from config import Settings


class RequestLog:
    """Wire-level record of what the test server received."""

    def __init__(self) -> None:
        self.batch_calls = 0
        self.batch_payloads: list[list[dict]] = []
        self.solve_bodies: list[dict] = []

    def record_batch(self, blocks: list[dict]) -> None:
        self.batch_calls += 1
        self.batch_payloads.append(blocks)

    def record_solve(self, body: dict) -> None:
        self.solve_bodies.append(body)


@pytest.fixture
def request_log() -> RequestLog:
    return RequestLog()


@pytest.fixture
def base_url(tmp_path: Path, request_log: RequestLog) -> Generator[str]:
    settings = Settings(
        _env_file=None,
        ocr_provider="fake",
        reasoning_provider="fake",
        results_dir=str(tmp_path / "results"),
    )
    application = create_app(settings=settings)
    _install_recorder(application, request_log)
    config = uvicorn.Config(application, host="127.0.0.1", port=0, log_level="critical", ws="none")
    server = uvicorn.Server(config)
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    started = time.monotonic()
    while not server.started:
        if time.monotonic() - started > 10.0:
            raise RuntimeError("test server failed to start")
        time.sleep(0.05)
    yield f"http://127.0.0.1:{server.servers[0].sockets[0].getsockname()[1]}"
    server.should_exit = True
    thread.join(timeout=5)


def _install_recorder(app: FastAPI, log: RequestLog) -> None:
    """HTTP middleware: observes the wire without touching route internals."""

    @app.middleware("http")
    async def record(request: Request, call_next):
        if request.url.path == "/api/v1/blocks/batch":
            body = await request.json()
            log.record_batch(body.get("blocks", []))
            # re-materialize the body for the route handler
            request._body = _dump(body)
        elif request.url.path == "/api/v1/blocks/solve":
            log.record_solve(await request.json())
        return await call_next(request)


def _dump(body: dict) -> bytes:
    import json

    return json.dumps(body).encode("utf-8")
