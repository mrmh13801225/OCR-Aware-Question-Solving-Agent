"""FastAPI app factory: the inbound adapter wiring settings to core."""

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from api.routes import blocks, providers, stream
from api.run_registry import RunEventLog
from config import Settings, configure_logging
from core.domain.errors import ProviderError
from persistence.json_repository import JSONFileResultRepository


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or Settings()
    configure_logging(settings.log_level, settings.log_file)
    app = FastAPI(title="OCR-Aware Question Solving Agent")
    app.state.run_registry = RunEventLog()
    app.state.repository = JSONFileResultRepository(results_dir=settings.results_dir)
    app.state.settings = settings
    app.include_router(blocks.router, prefix="/api/v1")
    app.include_router(providers.router, prefix="/api/v1")
    app.include_router(stream.router, prefix="/api/v1")

    @app.exception_handler(ProviderError)
    async def provider_error_handler(request: Request, exc: ProviderError) -> JSONResponse:
        # Vendor failures are upstream problems (bad gateway), not our bugs:
        # surface them cleanly instead of an unhandled 500. Our own errors
        # (ParseError, NoiseError) stay unhandled on purpose — a 500 is the
        # honest status for our-side bugs.
        return JSONResponse(status_code=502, content={"detail": str(exc)})

    return app


app = create_app()
