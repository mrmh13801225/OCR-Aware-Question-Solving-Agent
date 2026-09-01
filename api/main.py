"""FastAPI app factory: the inbound adapter wiring settings to core."""

from fastapi import FastAPI

from api.routes import blocks, providers, stream
from api.run_registry import RunEventLog
from config import Settings
from persistence.json_repository import JSONFileResultRepository


def create_app(results_dir: str = "./results", settings: Settings | None = None) -> FastAPI:
    app = FastAPI(title="OCR-Aware Question Solving Agent")
    app.state.run_registry = RunEventLog()
    app.state.repository = JSONFileResultRepository(results_dir=results_dir)
    app.state.settings = settings
    app.include_router(blocks.router, prefix="/api/v1")
    app.include_router(providers.router, prefix="/api/v1")
    app.include_router(stream.router, prefix="/api/v1")
    return app


app = create_app()
