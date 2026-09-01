"""Shared fixtures for CLI-layer tests: an ephemeral fake-provider API server."""

import threading
import time
from pathlib import Path

import pytest
import uvicorn

from api.main import create_app
from config import Settings


@pytest.fixture
def base_url(tmp_path: Path) -> str:
    settings = Settings(_env_file=None, ocr_provider="fake", reasoning_provider="fake")
    application = create_app(results_dir=tmp_path / "results", settings=settings)
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
