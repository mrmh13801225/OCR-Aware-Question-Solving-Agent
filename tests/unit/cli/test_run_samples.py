"""T4.5 — run_samples: health-check, solve each sample, write the brief's JSONL."""

import json
from pathlib import Path

import pytest


def test_writes_one_json_line_per_sample(tmp_path: Path, base_url: str) -> None:
    from scripts.run_samples import run

    samples = tmp_path / "samples"
    samples.mkdir()
    for name in ("q113.png", "q115.png"):
        (samples / name).write_bytes(b"fake-png")
    out_path = tmp_path / "results" / "samples.jsonl"

    run(samples_dir=samples, out_path=out_path, base_url=base_url)

    lines = out_path.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 2
    for line in lines:
        payload = json.loads(line)
        assert set(payload) == {"answer", "question_text", "changed", "original_ocr_text"}
        assert payload["answer"]


def test_health_check_down_fails_with_hint(tmp_path: Path) -> None:
    from scripts.run_samples import run

    samples = tmp_path / "samples"
    samples.mkdir()
    (samples / "q113.png").write_bytes(b"fake-png")
    with pytest.raises(SystemExit) as err:
        run(samples_dir=samples, out_path=tmp_path / "out.jsonl", base_url="http://127.0.0.1:9")
    assert "uvicorn" in str(err.value)
