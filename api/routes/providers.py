"""Providers route: what's registered, configured, and which models, for the UI selector."""

from fastapi import APIRouter, Request

from api.deps import effective_settings
from config import (
    FAKE_MODEL_NAME,
    OCR_PROVIDER_NAMES,
    REASONING_PROVIDER_NAMES,
    Settings,
)
from providers.reasoning.claude import MODEL as CLAUDE_MODEL

router = APIRouter()


def _default_models(settings: Settings) -> dict:
    return {
        "claude": CLAUDE_MODEL,
        "openai_compatible": settings.openai_compat_model,
        "local_vlm": settings.local_vlm_model,
        "fake": FAKE_MODEL_NAME,
    }


@router.get("/health")
def health() -> dict:
    return {"status": "ok"}


@router.get("/providers")
def providers(request: Request) -> dict:
    settings = effective_settings(request)
    return {
        "ocr": list(OCR_PROVIDER_NAMES),
        "reasoning": list(REASONING_PROVIDER_NAMES),
        "models": _default_models(settings),
        "configured": {"ocr": settings.ocr_provider, "reasoning": settings.reasoning_provider},
    }
