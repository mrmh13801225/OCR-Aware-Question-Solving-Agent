"""Typer + Rich CLI: a thin HTTP client of the local API — no direct provider calls.

The server owns everything: run `uvicorn api.main:app` first (README covers
this). The CLI never imports core or providers; it only speaks HTTP.
"""

import base64
import contextlib
import json
import sys
import threading
from pathlib import Path

import httpx
import typer
from rich.console import Console
from rich.panel import Panel
from rich.syntax import Syntax
from rich.table import Table

from api.routes.stream import DEFAULT_IDLE_TIMEOUT_SECONDS
from config import IMAGE_SUFFIXES

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

app = typer.Typer(help="OCR-aware question solving agent — API client.")
console = Console()

DEFAULT_BASE_URL = "http://127.0.0.1:8000"
SERVER_DOWN_HINT = "API server is not reachable. Start it with:  uvicorn api.main:app"
# The stream route closes itself after its idle timeout; wait that long plus
# a margin so a just-finished run's buffered events are fully drained.
TRACE_JOIN_MARGIN_SECONDS = 5.0


def http_client_for(base_url: str) -> httpx.Client:
    # trust_env=False: the API is local; a system HTTP proxy must never
    # intercept these requests (a proxy answering 503 would masquerade as
    # a reachable server).
    return httpx.Client(base_url=base_url, timeout=900.0, trust_env=False)


def _die(message: str) -> None:
    console.print(f"[red]{message}[/red]")
    raise typer.Exit(code=1)


def _request(client: httpx.Client, method: str, path: str, payload: dict | None = None) -> dict:
    try:
        response = client.request(method, path, json=payload)
    except httpx.HTTPError:
        _die(SERVER_DOWN_HINT)
    if response.status_code >= 400:
        _die(f"API error {response.status_code}: {response.text}")
    return response.json()


def _post(client: httpx.Client, path: str, payload: dict) -> dict:
    return _request(client, "POST", path, payload)


def _get(client: httpx.Client, path: str) -> dict:
    return _request(client, "GET", path)


def _encode_image(image_path: Path) -> str:
    try:
        return base64.b64encode(image_path.read_bytes()).decode("utf-8")
    except OSError as exc:
        _die(f"cannot read image {image_path}: {exc}")
        raise  # unreachable; narrows type for mypy


def _print_result(result: dict) -> None:
    verdict = (
        "UNRESOLVED" if result["unresolved"] else ("CHANGED" if result["changed"] else "UNCHANGED")
    )
    table = Table(show_header=False, box=None, padding=(0, 1))
    table.add_row("answer", f"[bold]{result['answer']}[/bold]")
    table.add_row("verdict", verdict)
    table.add_row("attempts", str(result["attempts"]))
    console.print(Panel(table, title="Result", expand=False))
    console.print(
        Syntax(json.dumps(result, ensure_ascii=False, indent=2), "json", theme="ansi_dark")
    )


@app.command()
def solve(
    image_path: Path = typer.Argument(..., exists=True, readable=True),
    base_url: str = typer.Option(DEFAULT_BASE_URL, "--base-url"),
    inject_noise: bool = typer.Option(False, "--inject-noise"),
    trace: bool = typer.Option(False, "--trace", help="Stream retry-loop events live."),
) -> None:
    """Solve one question block image through the API."""
    run_id = f"cli-{image_path.stem}"
    payload = {
        "image_base64": _encode_image(image_path),
        "inject_noise": inject_noise,
        "run_id": run_id,
    }
    with http_client_for(base_url) as client:
        if trace:
            with _trace_reader(client, run_id):
                result = _post(client, "/api/v1/blocks/solve", payload)
        else:
            result = _post(client, "/api/v1/blocks/solve", payload)
    _print_result(result)


@contextlib.contextmanager
def _trace_reader(client: httpx.Client, run_id: str):
    """Stream-first SSE reader: opened before the solve, per API_SPEC.

    Runs on a daemon thread that prints each event as it arrives; the
    context closes when the stream ends (terminal or TIMEOUT event).
    """
    lines: list[str] = []

    def read_stream() -> None:
        try:
            with client.stream("GET", f"/api/v1/blocks/{run_id}/stream") as response:
                for line in response.iter_lines():
                    if line.startswith("data: "):
                        lines.append(line)
        except httpx.HTTPError:
            return  # trace is best-effort; the solve result is authoritative

    thread = threading.Thread(target=read_stream, daemon=True)
    thread.start()
    try:
        yield
    finally:
        thread.join(timeout=DEFAULT_IDLE_TIMEOUT_SECONDS + TRACE_JOIN_MARGIN_SECONDS)
        for line in lines:
            try:
                event = json.loads(line.removeprefix("data: "))
            except json.JSONDecodeError:
                continue
            if event["run_state"] == "TIMEOUT":
                console.print("[red]trace ended: run never arrived (TIMEOUT)[/red]")
            else:
                state = event["run_state"]
                index = event["attempt_index"]
                console.print(f"[muted]{state} · {index} · {event['detail']}[/muted]")


@app.command()
def batch(
    directory: Path = typer.Argument(..., exists=True, file_okay=False),
    out: Path = typer.Option(None, "--out", help="Optional local JSONL copy of the results."),
    base_url: str = typer.Option(DEFAULT_BASE_URL, "--base-url"),
) -> None:
    """Solve every image in a directory with one batch call; the server persists results."""
    images = sorted(p for p in directory.iterdir() if p.suffix.lower() in IMAGE_SUFFIXES)
    if not images:
        _die(f"no images found in {directory}")
    blocks = [
        {"image_base64": _encode_image(image_path), "run_id": f"cli-{image_path.stem}"}
        for image_path in images
    ]
    with http_client_for(base_url) as client:
        body = _post(client, "/api/v1/blocks/batch", {"blocks": blocks})
    results = body["results"]
    for image_path, result in zip(images, results, strict=True):
        console.print(f"[muted]{image_path.name} -> {result['answer']}[/muted]")
    if out is not None:
        out.parent.mkdir(parents=True, exist_ok=True)
        # the local artifact matches the brief's deliverable schema exactly,
        # not the fuller API response
        deliverable_fields = ("answer", "question_text", "changed", "original_ocr_text")
        projected = [{field: r[field] for field in deliverable_fields} for r in results]
        out.write_text(
            "\n".join(json.dumps(r, ensure_ascii=False) for r in projected) + "\n",
            encoding="utf-8",
        )
        console.print(f"[green]Wrote {len(results)} results to {out}[/green]")
    else:
        console.print(
            f"[green]{len(results)} results saved server-side (GET /api/v1/results)[/green]"
        )


@app.command()
def providers(
    base_url: str = typer.Option(DEFAULT_BASE_URL, "--base-url"),
) -> None:
    """List registered providers and configured defaults."""
    with http_client_for(base_url) as client:
        body = _get(client, "/api/v1/providers")
    table = Table(title="Providers")
    table.add_column("kind")
    table.add_column("registered")
    table.add_column("configured")
    table.add_row("OCR", ", ".join(body["ocr"]), body["configured"]["ocr"])
    table.add_row("reasoning", ", ".join(body["reasoning"]), body["configured"]["reasoning"])
    console.print(table)


if __name__ == "__main__":
    app()
