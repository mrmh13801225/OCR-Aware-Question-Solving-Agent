"""FastAPI app factory: the inbound adapter wiring settings to core."""

import base64

from fastapi import FastAPI, Request

from api.routes import blocks, providers, stream
from api.run_registry import RunEventLog
from persistence.json_repository import JSONFileResultRepository


def create_app(results_dir: str = "./results", settings=None) -> FastAPI:
    app = FastAPI(title="OCR-Aware Question Solving Agent")
    app.state.run_registry = RunEventLog()
    app.state.repository = JSONFileResultRepository(results_dir=results_dir)
    app.state.settings = settings
    app.include_router(blocks.router, prefix="/api/v1")
    app.include_router(providers.router, prefix="/api/v1")
    app.include_router(stream.router, prefix="/api/v1")
    return app


def decode_image(image_base64: str) -> bytes:
    return base64.b64decode(image_base64)


def effective_settings(request: Request):
    from config import Settings

    return request.app.state.settings or Settings()


app = create_app()
