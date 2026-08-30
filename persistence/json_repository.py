"""Flat-JSON persistence of BlockResults — one file per result, atomic writes."""

import json
import os
import uuid
from dataclasses import asdict
from pathlib import Path

from core.domain.models import BlockResult
from core.domain.ports import ResultRepository


class JSONFileResultRepository(ResultRepository):
    """Repository port implementation over flat JSON files under results_dir."""

    def __init__(self, results_dir: str | Path) -> None:
        self._dir = Path(results_dir)

    def save(self, result: BlockResult) -> None:
        self._dir.mkdir(parents=True, exist_ok=True)
        target = self._dir / f"{uuid.uuid4().hex}.json"
        # Write-then-replace: a crash mid-write leaves a .tmp, never a partial
        # result at the target path.
        tmp = target.with_suffix(".tmp")
        tmp.write_text(json.dumps(asdict(result), ensure_ascii=False), encoding="utf-8")
        os.replace(tmp, target)

    def list(self) -> list[BlockResult]:
        if not self._dir.is_dir():
            return []
        results = []
        for path in sorted(self._dir.glob("*.json")):
            data = json.loads(path.read_text(encoding="utf-8"))
            results.append(BlockResult(**data))
        return results
