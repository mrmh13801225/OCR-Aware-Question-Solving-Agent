"""Produce the required deliverable: one JSON object per sample block.

Usage (API server must be running):
    uvicorn api.main:app
    python scripts/run_samples.py --samples tests/fixtures/samples --out results/samples.jsonl
"""

import argparse
import base64
import json
import sys
from pathlib import Path

import httpx

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

SERVER_DOWN_HINT = "API server is not reachable. Start it with:  uvicorn api.main:app"
DELIVERABLE_FIELDS = ("answer", "question_text", "changed", "original_ocr_text")


def run(samples_dir: Path, out_path: Path, base_url: str) -> None:
    # generous client timeout: a correction call against a slow reasoning
    # gateway measured at ~7 minutes server-side
    client = httpx.Client(base_url=base_url, timeout=900.0, trust_env=False)
    _require_server(client)

    images = sorted(
        p for p in samples_dir.iterdir() if p.suffix.lower() in {".png", ".jpg", ".jpeg", ".webp"}
    )
    if not images:
        raise SystemExit(f"no images found in {samples_dir}")

    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", encoding="utf-8") as out:
        for image_path in images:
            result = _solve(client, image_path)
            deliverable = {field: result[field] for field in DELIVERABLE_FIELDS}
            out.write(json.dumps(deliverable, ensure_ascii=False) + "\n")
            print(f"{image_path.name}: {deliverable['answer']}")
    print(f"Wrote {len(images)} deliverable objects to {out_path}")


def _require_server(client: httpx.Client) -> None:
    try:
        response = client.get("/api/v1/health")
        response.raise_for_status()
    except httpx.HTTPError:
        raise SystemExit(SERVER_DOWN_HINT) from None


def _solve(client: httpx.Client, image_path: Path) -> dict:
    payload = {
        "image_base64": base64.b64encode(image_path.read_bytes()).decode("utf-8"),
        "run_id": f"samples-{image_path.stem}",
    }
    response = client.post("/api/v1/blocks/solve", json=payload)
    if response.status_code >= 400:
        raise SystemExit(f"API error {response.status_code} for {image_path.name}: {response.text}")
    return response.json()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--samples", type=Path, default=Path("tests/fixtures/samples"))
    parser.add_argument("--out", type=Path, default=Path("results/samples.jsonl"))
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    arguments = parser.parse_args()
    run(samples_dir=arguments.samples, out_path=arguments.out, base_url=arguments.base_url)


if __name__ == "__main__":
    main()
