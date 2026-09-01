"""Typer + Rich CLI: a thin HTTP client of the local API — no direct provider calls.

The server owns everything: run `uvicorn api.main:app` first (README covers
this). The CLI never imports core or providers; it only speaks HTTP.
"""

import base64
import json
import sys
from pathlib import Path

import httpx
import typer
from rich.console import Console
from rich.panel import Panel
from rich.syntax import Syntax
from rich.table import Table

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

app = typer.Typer(help="OCR-aware question solving agent — API client.")
console = Console()

DEFAULT_BASE_URL = "http://127.0.0.1:8000"
SERVER_DOWN_HINT = "API server is not reachable. Start it with:  uvicorn api.main:app"


def http_client_for(base_url: str) -> httpx.Client:
    # trust_env=False: the API is local; a system HTTP proxy must never
    # intercept these requests (a proxy answering 503 would masquerade as
    # a reachable server).
    return httpx.Client(base_url=base_url, timeout=300.0, trust_env=False)


def _die(message: str) -> None:
    console.print(f"[red]{message}[/red]")
    raise typer.Exit(code=1)


def _post(client: httpx.Client, path: str, payload: dict) -> dict:
    try:
        response = client.post(path, json=payload)
    except httpx.HTTPError:
        _die(SERVER_DOWN_HINT)
    if response.status_code >= 400:
        _die(f"API error {response.status_code}: {response.text}")
    return response.json()


def _get(client: httpx.Client, path: str) -> dict:
    try:
        response = client.get(path)
    except httpx.HTTPError:
        _die(SERVER_DOWN_HINT)
    if response.status_code >= 400:
        _die(f"API error {response.status_code}: {response.text}")
    return response.json()


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
) -> None:
    """Solve one question block image through the API."""
    payload = {
        "image_base64": _encode_image(image_path),
        "inject_noise": inject_noise,
        "run_id": f"cli-{image_path.stem}",
    }
    with http_client_for(base_url) as client:
        result = _post(client, "/api/v1/blocks/solve", payload)
    _print_result(result)


@app.command()
def batch(
    directory: Path = typer.Argument(..., exists=True, file_okay=False),
    out: Path = typer.Option("results/cli_batch.jsonl", "--out"),
    base_url: str = typer.Option(DEFAULT_BASE_URL, "--base-url"),
) -> None:
    """Solve every image in a directory; write one JSON line per result."""
    images = sorted(
        p for p in directory.iterdir() if p.suffix.lower() in {".png", ".jpg", ".jpeg", ".webp"}
    )
    if not images:
        _die(f"no images found in {directory}")
    lines = []
    with http_client_for(base_url) as client:
        for image_path in images:
            payload = {
                "image_base64": _encode_image(image_path),
                "run_id": f"cli-{image_path.stem}",
            }
            lines.append(_post(client, "/api/v1/blocks/solve", payload))
            console.print(f"[muted]{image_path.name} -> {lines[-1]['answer']}[/muted]")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(
        "\n".join(json.dumps(line, ensure_ascii=False) for line in lines) + "\n", encoding="utf-8"
    )
    console.print(f"[green]Wrote {len(lines)} results to {out}[/green]")


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
