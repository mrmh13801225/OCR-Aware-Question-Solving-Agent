"""Blocks routes: solve, batch, results — thin HTTP over the retry loop."""

import base64

from fastapi import APIRouter, Request

from api.schemas import BlockResultResponse, SolveRequest
from config import build_ocr_provider, build_reasoning_provider
from core.services.noise_injector import NoiseInjector
from core.services.retry_loop import RetryLoop

router = APIRouter()


class _RunListener:
    """Forwards loop events into the registry under the request's run_id."""

    def __init__(self, registry, run_id: str) -> None:
        self._registry = registry
        self._run_id = run_id

    def on_event(self, event) -> None:
        self._registry.on_event(event, run_id=self._run_id)


def _solve_one(request: Request, body: SolveRequest):
    from api.main import effective_settings

    settings = effective_settings(request)
    ocr_name = body.ocr_provider or settings.ocr_provider
    reasoning_name = body.reasoning_provider or settings.reasoning_provider
    ocr = build_ocr_provider(ocr_name, settings)
    reasoning = build_reasoning_provider(reasoning_name, settings)

    registry = request.app.state.run_registry
    listener = _RunListener(registry, body.run_id) if body.run_id else registry
    injector = NoiseInjector(rate=settings.noise_rate, seed=42) if body.inject_noise else None

    loop = RetryLoop(
        ocr=ocr,
        reasoning=reasoning,
        listener=listener,
        retry_cap=settings.retry_cap,
        injector=injector,
        answer_mapping=body.answer_mapping or settings.answer_mapping,
    )

    image = base64.b64decode(body.image_base64)
    if body.ocr_text is not None:
        result = _solve_with_preloaded_text(
            loop, reasoning, body.ocr_text, image, settings, injector
        )
    else:
        result = loop.solve_block(image)

    request.app.state.repository.save(result)
    return BlockResultResponse.from_domain(result)


def _solve_with_preloaded_text(loop, reasoning, ocr_text: str, image: bytes, settings, injector):
    from core.services.block_parser import parse

    block = parse(ocr_text)
    if injector is not None:
        block = injector.corrupt(block)

    from core.domain.models import BlockResult
    from core.services.answer_matcher import matches, resolve_letter
    from core.services.best_guess import pick_best

    attempts = []
    for attempt_index in range(settings.retry_cap + 1):
        attempt = reasoning.solve(image, block.question_text, block.options)
        attempts.append(attempt)
        if matches(attempt.raw_answer, block.options):
            answer = resolve_letter(loop.answer_mapping, attempt.raw_answer, block.options)
            return BlockResult(
                answer=answer or attempt.raw_answer,
                question_text=block.question_text,
                changed=attempt_index > 0,
                original_ocr_text=ocr_text,
                attempts=len(attempts),
            )
        if attempt_index < settings.retry_cap:
            block = reasoning.correct(image, block, attempt.raw_answer)
    answer = pick_best(attempts, block.options)
    return BlockResult(
        answer=answer,
        question_text=block.question_text,
        changed=True,
        original_ocr_text=ocr_text,
        unresolved=True,
        attempts=len(attempts),
    )


@router.post("/blocks/solve", response_model=BlockResultResponse)
def solve(body: SolveRequest, request: Request) -> BlockResultResponse:
    return _solve_one(request, body)


@router.post("/blocks/batch")
def batch(body: dict, request: Request) -> dict:
    results = []
    for block in body.get("blocks", []):
        results.append(_solve_one(request, SolveRequest(**block)))
    return {"results": [r.model_dump() for r in results]}


@router.get("/results")
def results(request: Request) -> dict:
    saved = request.app.state.repository.list()
    return {"results": [BlockResultResponse.from_domain(r).model_dump() for r in saved]}
