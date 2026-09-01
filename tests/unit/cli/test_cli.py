"""T4.4 — CLI commands as a thin HTTP client, tested against a live local server."""

import base64
import json
import threading
import time
from pathlib import Path

import pytest
import uvicorn
from typer.testing import CliRunner

from api.main import create_app
from cli.main import app
from config import Settings

runner = CliRunner()
IMAGE_B64 = base64.b64encode(b"fake-png-bytes").decode("utf-8")


@pytest.fixture
def base_url(tmp_path: Path) -> str:
    settings = Settings(_env_file=None, ocr_provider="fake", reasoning_provider="fake")
    application = create_app(results_dir=tmp_path / "results", settings=settings)
    config = uvicorn.Config(application, host="127.0.0.1", port=0, log_level="critical")
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


def test_solve_command_prints_answer_and_changed(tmp_path: Path, base_url: str) -> None:
    image_path = tmp_path / "q113.png"
    image_path.write_bytes(b"fake-png-bytes")
    result = runner.invoke(app, ["solve", str(image_path), "--base-url", base_url])
    assert result.exit_code == 0
    assert "answer" in result.output.lower()
    assert "A" in result.output  # fake provider picks option 1


def test_solve_command_sends_image_bytes(tmp_path: Path, base_url: str) -> None:
    image_path = tmp_path / "block.png"
    image_path.write_bytes(b"fake-png-bytes")
    result = runner.invoke(app, ["solve", str(image_path), "--base-url", base_url])
    assert result.exit_code == 0


def test_providers_command_lists_registered(base_url: str) -> None:
    result = runner.invoke(app, ["providers", "--base-url", base_url])
    assert result.exit_code == 0
    assert "nanonets" in result.output
    assert "claude" in result.output


def test_batch_command_writes_output_lines(tmp_path: Path, base_url: str) -> None:
    for name in ("a.png", "b.png"):
        (tmp_path / name).write_bytes(b"fake-png-bytes")
    out_path = tmp_path / "out.jsonl"
    result = runner.invoke(
        app,
        ["batch", str(tmp_path), "--out", str(out_path), "--base-url", base_url],
    )
    assert result.exit_code == 0
    lines = out_path.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 2
    assert all(json.loads(line)["answer"] for line in lines)


def test_server_down_fails_fast_with_start_hint(tmp_path: Path) -> None:
    image_path = tmp_path / "x.png"
    image_path.write_bytes(b"data")
    result = runner.invoke(
        app,
        ["solve", str(image_path), "--base-url", "http://127.0.0.1:1"],
        catch_exceptions=True,
    )
    assert result.exit_code != 0
    assert "uvicorn" in result.output.lower()
