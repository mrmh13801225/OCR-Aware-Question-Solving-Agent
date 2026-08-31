"""Shared HTTP plumbing for adapters: status mapping and vendor-call wrapping.

Every adapter must map vendor failures onto the same typed ProviderError
hierarchy — extracting that mapping here is what makes the guarantee
structural rather than per-adapter discipline (same rationale as the
reasoning prompts/replies modules).
"""

import json
from collections.abc import Callable

import httpx

from core.domain.errors import (
    ProviderAuthError,
    ProviderRateLimitError,
    ProviderResponseError,
    ProviderTimeoutError,
)


def raise_for_status(response: httpx.Response, provider: str) -> None:
    """Map non-2xx vendor responses onto the typed error hierarchy."""
    if response.status_code == 401:
        raise ProviderAuthError(response.text, provider=provider)
    if response.status_code == 429:
        raise ProviderRateLimitError(response.text, provider=provider)
    if response.status_code >= 400:
        raise ProviderResponseError(response.text, provider=provider)


def json_field(response: httpx.Response, provider: str) -> dict:
    """Parse a JSON-object body; anything else is a ProviderResponseError."""
    try:
        data = response.json()
        if not isinstance(data, dict):
            raise TypeError("expected a JSON object")
        return data
    except (json.JSONDecodeError, TypeError) as exc:
        raise ProviderResponseError(
            f"malformed reply from vendor: {exc}", provider=provider
        ) from exc


def call_vendor(
    provider: str,
    request: Callable[[], httpx.Response],
) -> httpx.Response:
    """Run one vendor HTTP call, wrapping transport failures as ProviderErrors."""
    try:
        return request()
    except httpx.TimeoutException as exc:
        raise ProviderTimeoutError(str(exc), provider=provider) from exc
    except httpx.HTTPError as exc:
        raise ProviderTimeoutError(f"connection failed: {exc}", provider=provider) from exc
