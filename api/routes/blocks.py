"""Blocks routes: solve, batch, results — thin HTTP over the retry loop."""

import base64
import binascii

from fastapi import APIRouter, HTTPException, Request

from api.deps import effective_settings
from api.run_registry import RunEventLog
from api.schemas import BatchRequest, BlockResultResponse, SolveRequest
from config import build_ocr_provider, build_reasoning_provider
from core.domain.ports import OCRText, RunEvent, RunEventListener
from core.services.noise_injector import NoiseInjector
from core.services.retry_loop import RetryLoop

router = APIRouter()


class _RunListener:
    """Forwards loop events into the registry under the request's run_id."""

    def __init__(self, registry: RunEventLog, run_id: str) -> None:
        self._registry = registry
        self._run_id = run_id

    def on_event(self, event: RunEvent) -> None:
        self._registry.on_event(event, run_id=self._run_id)


def _solve_one(request: Request, body: SolveRequest) -> BlockResultResponse:
    settings = effective_settings(request)
    ocr_name = body.ocr_provider or settings.ocr_provider
    reasoning_name = body.reasoning_provider or settings.reasoning_provider
    ocr = build_ocr_provider(ocr_name, settings)
    reasoning = build_reasoning_provider(
        reasoning_name, settings, solve_mode=body.solve_mode
    )

    registry = request.app.state.run_registry
    listener: RunEventListener = _RunListener(registry, body.run_id) if body.run_id else registry
    injector = (
        NoiseInjector(rate=settings.noise_rate, seed=settings.noise_seed)
        if body.inject_noise
        else None
    )

    loop = RetryLoop(
        ocr=ocr,
        reasoning=reasoning,
        listener=listener,
        retry_cap=settings.retry_cap,
        injector=injector,
        answer_mapping=body.answer_mapping or settings.answer_mapping,
    )

    try:
        image = base64.b64decode(body.image_base64, validate=True)
    except (binascii.Error, ValueError) as exc:
        raise HTTPException(status_code=422, detail="image_base64 is not valid base64") from exc

    extracted = (
        OCRText(text=body.ocr_text, provider="client") if body.ocr_text is not None else None
    )
    result = loop.solve_block(image, extracted=extracted)

    request.app.state.repository.save(result)
    return BlockResultResponse.from_domain(result)


@router.post("/blocks/solve", response_model=BlockResultResponse)
def solve(body: SolveRequest, request: Request) -> BlockResultResponse:
    return _solve_one(request, body)


@router.post("/blocks/batch")
def batch(body: BatchRequest, request: Request) -> dict:
    results = [_solve_one(request, block) for block in body.blocks]
    return {"results": [r.model_dump() for r in results]}


@router.get("/results")
def results(request: Request) -> dict:
    saved = request.app.state.repository.list()
    return {"results": [BlockResultResponse.from_domain(r).model_dump() for r in saved]}
