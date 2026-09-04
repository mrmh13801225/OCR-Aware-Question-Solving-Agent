"""In-memory run event registry: bounded ring per run_id, TTL eviction.

Feeds the SSE stream. Runs are process-local — a uvicorn --reload restart
wipes them, which API_SPEC documents as a known limitation.
"""

import time
from collections import deque
from collections.abc import Iterator

from core.domain.models import TERMINAL_RUN_STATES
from core.domain.ports import RunEvent, RunEventListener

MAX_EVENTS_PER_RUN = 200
RUN_TTL_SECONDS = 600.0
MAX_RUNS = 100


class RunEventLog(RunEventListener):
    """Observer-port implementation buffering one run's events for replay+follow."""

    def __init__(self) -> None:
        self._events: dict[str, deque[RunEvent]] = {}
        self._finished: dict[str, bool] = {}
        self._last_activity: dict[str, float] = {}

    def on_event(self, event: RunEvent, run_id: str = "") -> None:
        if not run_id:
            return
        ring = self._events.setdefault(run_id, deque(maxlen=MAX_EVENTS_PER_RUN))
        ring.append(event)
        self._last_activity[run_id] = time.monotonic()
        if event.run_state in TERMINAL_RUN_STATES:
            self._finished[run_id] = True
        self._evict()

    def events(self, run_id: str) -> list[RunEvent]:
        return list(self._events.get(run_id, ()))

    def is_finished(self, run_id: str) -> bool:
        return self._finished.get(run_id, False)

    def stream_from(self, run_id: str, after: int = 0) -> Iterator[RunEvent]:
        for index, event in enumerate(self._events.get(run_id, ())):
            if index >= after:
                yield event

    def _evict(self) -> None:
        now = time.monotonic()
        stale = [
            run_id for run_id, seen in self._last_activity.items() if now - seen > RUN_TTL_SECONDS
        ]
        for run_id in stale:
            self._drop(run_id)
        while len(self._events) > MAX_RUNS:
            oldest = min(self._last_activity, key=self._last_activity.get)  # type: ignore[arg-type]
            self._drop(oldest)

    def _drop(self, run_id: str) -> None:
        self._events.pop(run_id, None)
        self._finished.pop(run_id, None)
        self._last_activity.pop(run_id, None)
