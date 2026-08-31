"""SSE stream route: replay buffered events, then follow until terminal."""

import asyncio
import json

from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse

IDLE_TIMEOUT_SECONDS = 60.0
POLL_INTERVAL_SECONDS = 0.1

router = APIRouter()


@router.get("/blocks/{run_id}/stream")
async def stream(run_id: str, request: Request) -> StreamingResponse:
    """Stream one run's retry-loop events.

    Per API_SPEC the client may open this stream BEFORE issuing the solve
    call — an unknown run_id is legal: the stream follows, waiting for
    events, until the run terminates or the idle timeout expires.
    """
    registry = request.app.state.run_registry

    async def event_source():
        sent = 0
        idle_for = 0.0
        while True:
            new_events = list(registry.stream_from(run_id, after=sent))
            for event in new_events:
                payload = json.dumps(
                    {
                        "run_state": event.run_state,
                        "attempt_index": event.attempt_index,
                        "detail": event.detail,
                    },
                    ensure_ascii=False,
                )
                yield f"data: {payload}\n\n"
                sent += 1
                idle_for = 0.0
            if registry.is_finished(run_id) and sent >= len(registry.events(run_id)):
                return
            if not new_events:
                idle_for += POLL_INTERVAL_SECONDS
                if idle_for > IDLE_TIMEOUT_SECONDS:
                    return
            await asyncio.sleep(POLL_INTERVAL_SECONDS)

    return StreamingResponse(event_source(), media_type="text/event-stream")
