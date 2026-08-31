"""Request-scoped dependencies shared by routes (cycle-free: imports nothing from api)."""

from fastapi import Request

from config import Settings


def effective_settings(request: Request) -> Settings:
    """The app's injected settings, or env-loaded Settings when not overridden."""
    return request.app.state.settings or Settings()
