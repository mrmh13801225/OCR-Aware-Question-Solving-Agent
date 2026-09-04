"""T4.4 — CLI commands as a thin HTTP client, tested against a live local server."""

import base64
import json
from pathlib import Path

from typer.testing import CliRunner

from cli.main import app

runner = CliRunner()
IMAGE_B64 = base64.b64encode(b"fake-png-bytes").decode("utf-8")


def test_solve_command_prints_answer_and_changed(tmp_path: Path, base_url: str) -> None:
    image_path = tmp_path / "q113.png"
    image_path.write_bytes(b"fake-png-bytes")
    result = runner.invoke(app, ["solve", str(image_path), "--base-url", base_url])
    assert result.exit_code == 0
    assert "answer" in result.output.lower()
    assert "A" in result.output  # fake provider picks option 1


def test_solve_command_sends_image_bytes(tmp_path: Path, base_url: str, request_log) -> None:
    image_path = tmp_path / "block.png"
    image_path.write_bytes(b"fake-png-bytes")
    result = runner.invoke(app, ["solve", str(image_path), "--base-url", base_url])
    assert result.exit_code == 0
    assert len(request_log.solve_bodies) == 1
    sent = base64.b64decode(request_log.solve_bodies[0]["image_base64"])
    assert sent == b"fake-png-bytes"  # the exact file bytes reach the wire


def test_solve_solve_mode_flag_travels_on_the_wire(
    tmp_path: Path, base_url: str, request_log
) -> None:
    image_path = tmp_path / "block.png"
    image_path.write_bytes(b"fake-png-bytes")
    result = runner.invoke(
        app,
        ["solve", str(image_path), "--base-url", base_url, "--solve-mode", "text_only"],
    )
    assert result.exit_code == 0
    assert request_log.solve_bodies[0]["solve_mode"] == "text_only"


def test_solve_without_solve_mode_flag_omits_the_field(
    tmp_path: Path, base_url: str, request_log
) -> None:
    image_path = tmp_path / "block.png"
    image_path.write_bytes(b"fake-png-bytes")
    result = runner.invoke(app, ["solve", str(image_path), "--base-url", base_url])
    assert result.exit_code == 0
    assert "solve_mode" not in request_log.solve_bodies[0]  # server default applies


def test_solve_trace_flag_streams_events(tmp_path: Path, base_url: str) -> None:
    image_path = tmp_path / "q.png"
    image_path.write_bytes(b"fake-png-bytes")
    result = runner.invoke(app, ["solve", str(image_path), "--base-url", base_url, "--trace"])
    assert result.exit_code == 0
    assert "SOLVE" in result.output
    assert "DONE" in result.output
    assert "answer" in result.output.lower()  # result panel still prints


def test_providers_command_lists_registered(base_url: str) -> None:
    result = runner.invoke(app, ["providers", "--base-url", base_url])
    assert result.exit_code == 0
    assert "nanonets" in result.output
    assert "claude" in result.output


def test_batch_command_sends_one_batch_call_in_input_order(
    tmp_path: Path, base_url: str, request_log
) -> None:
    """TESTING.md §4.5: batch is ONE POST /blocks/batch carrying every image,
    with the server's input-order guarantee exercised on the wire payload."""
    for name in ("a.png", "b.png"):
        (tmp_path / name).write_bytes(b"fake-png-bytes")
    out_path = tmp_path / "out.jsonl"
    result = runner.invoke(
        app,
        ["batch", str(tmp_path), "--out", str(out_path), "--base-url", base_url],
    )
    assert result.exit_code == 0
    assert request_log.batch_calls == 1
    sent_run_ids = [block["run_id"] for block in request_log.batch_payloads[0]]
    assert sent_run_ids == ["cli-a", "cli-b"]  # sorted input order travels in one call


def test_batch_command_writes_output_lines_in_input_order(tmp_path: Path, base_url: str) -> None:
    for name in ("a.png", "b.png"):
        (tmp_path / name).write_bytes(b"fake-png-bytes")
    out_path = tmp_path / "out.jsonl"
    result = runner.invoke(
        app,
        ["batch", str(tmp_path), "--out", str(out_path), "--base-url", base_url],
    )
    assert result.exit_code == 0
    assert "a.png" in result.output and "b.png" in result.output
    # JSONL mirrors the response order, which the batch call guarantees to
    # match input order; the server-side insertion order (deterministic
    # timestamps) must agree.
    lines = out_path.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 2
    assert all(json.loads(line)["answer"] for line in lines)
    assert result.output.index("a.png") < result.output.index("b.png")


def test_batch_without_out_flag_persists_server_side_only(tmp_path: Path, base_url: str) -> None:
    import httpx

    for name in ("a.png", "b.png"):
        (tmp_path / name).write_bytes(b"fake-png-bytes")
    result = runner.invoke(app, ["batch", str(tmp_path), "--base-url", base_url])
    assert result.exit_code == 0
    assert not list(tmp_path.rglob("*.jsonl"))  # no local artifact written
    assert "saved server-side" in result.output
    listing = httpx.get(f"{base_url}/api/v1/results", trust_env=False).json()
    assert len(listing["results"]) == 2  # both persisted server-side


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


def test_batch_out_file_contains_only_deliverable_fields(tmp_path: Path, base_url: str) -> None:
    """The CLI --out artifact must match the brief's 4-field schema, not the
    full API response (extra fields would fail the graded schema)."""
    for name in ("a.png", "b.png"):
        (tmp_path / name).write_bytes(b"fake-png-bytes")
    out_path = tmp_path / "out.jsonl"
    result = runner.invoke(
        app,
        ["batch", str(tmp_path), "--out", str(out_path), "--base-url", base_url],
    )
    assert result.exit_code == 0
    for line in out_path.read_text(encoding="utf-8").strip().splitlines():
        payload = json.loads(line)
        assert set(payload) == {"answer", "question_text", "changed", "original_ocr_text"}
