"""T2.4 — flat-JSON result repository: atomic writes, round-trip, RESULTS_DIR."""

import json
from pathlib import Path

from core.domain.models import BlockResult
from persistence.json_repository import JSONFileResultRepository


def _result(answer: str = "C") -> BlockResult:
    return BlockResult(answer=answer, question_text="q", changed=False, original_ocr_text="o")


def test_save_writes_flat_json_file(tmp_path: Path) -> None:
    repo = JSONFileResultRepository(results_dir=tmp_path)
    repo.save(_result())
    files = list(tmp_path.glob("*.json"))
    assert len(files) == 1
    payload = json.loads(files[0].read_text(encoding="utf-8"))
    assert payload["answer"] == "C"
    assert payload["original_ocr_text"] == "o"


def test_list_round_trips_results(tmp_path: Path) -> None:
    repo = JSONFileResultRepository(results_dir=tmp_path)
    repo.save(_result("A"))
    repo.save(_result("B"))
    results = repo.list()
    assert [r.answer for r in results] == ["A", "B"]
    assert all(isinstance(r, BlockResult) for r in results)


def test_list_empty_returns_empty_list(tmp_path: Path) -> None:
    assert JSONFileResultRepository(results_dir=tmp_path).list() == []


def test_write_is_atomic(tmp_path: Path) -> None:
    repo = JSONFileResultRepository(results_dir=tmp_path)
    repo.save(_result("A"))
    # Each save writes to a fresh tmp file and replaces it into place: the
    # target json never exists in a partial state, and no tmp residue remains.
    repo.save(_result("B"))
    files = sorted(tmp_path.glob("*.json"))
    assert len(files) == 2
    answers = {json.loads(f.read_text(encoding="utf-8"))["answer"] for f in files}
    assert answers == {"A", "B"}
    assert not list(tmp_path.glob("*.tmp"))


def test_results_dir_created_if_missing(tmp_path: Path) -> None:
    nested = tmp_path / "deep" / "results"
    JSONFileResultRepository(results_dir=nested).save(_result())
    assert nested.is_dir()
    assert len(list(nested.glob("*.json"))) == 1


def test_each_result_gets_unique_file(tmp_path: Path) -> None:
    repo = JSONFileResultRepository(results_dir=tmp_path)
    repo.save(_result("A"))
    repo.save(_result("B"))
    assert len(list(tmp_path.glob("*.json"))) == 2
    assert len(repo.list()) == 2
