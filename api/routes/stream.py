"""SSE stream route: replay buffered events, then follow until terminal."""

import asyncio
import json

from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse

router = APIRouter()


@router.get("/blocks/{run_id}/stream")
async def stream(run_id: str, request: Request) -> StreamingResponse:
    registry = request.app.state.run_registry
    if not registry.known(run_id):
        return StreamingResponse(iter([]), status_code=404)

    async def event_source():
        sent = 0
        while True:
            events = registry.stream_from(run_id, after=sent)
            for event in events:
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
            if registry.is_finished(run_id):
                return
            await asyncio.sleep(0.1)

    return StreamingResponse(event_source(), media_type="text/event-stream")
