"""Providers route: what's registered and what's configured, for the UI selector."""

from fastapi import APIRouter, Request

from config import (
    OCR_PROVIDER_NAMES,
    REASONING_PROVIDER_NAMES,
)

router = APIRouter()


@router.get("/health")
def health() -> dict:
    return {"status": "ok"}


@router.get("/providers")
def providers(request: Request) -> dict:
    from api.deps import effective_settings

    settings = effective_settings(request)
    return {
        "ocr": list(OCR_PROVIDER_NAMES),
        "reasoning": list(REASONING_PROVIDER_NAMES),
        "configured": {"ocr": settings.ocr_provider, "reasoning": settings.reasoning_provider},
    }
