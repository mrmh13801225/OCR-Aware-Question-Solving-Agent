"""Shared HTTP plumbing for adapters: status mapping and vendor-call wrapping.

Every adapter must map vendor failures onto the same typed ProviderError
hierarchy — extracting that mapping here is what makes the guarantee
structural rather than per-adapter discipline (same rationale as the
reasoning prompts/replies modules).
"""

import json
from collections.abc import Callable
from urllib.parse import urlparse

import httpx

from core.domain.errors import (
    ProviderAuthError,
    ProviderRateLimitError,
    ProviderResponseError,
    ProviderTimeoutError,
)

LOCAL_HOSTS = {"localhost", "127.0.0.1", "::1", "0.0.0.0"}


def trust_env_for(base_url: str) -> bool:
    """Whether httpx should honor system proxy env vars for this endpoint.

    External vendors on a proxy-gated network NEED the system proxy;
    local endpoints (vLLM/Ollama gateways on localhost) must NEVER be
    proxied — a proxy answering for them yields bogus timeouts or 503s.
    """
    return urlparse(base_url).hostname not in LOCAL_HOSTS


def raise_for_status(response: httpx.Response, provider: str) -> None:
    """Map non-2xx vendor responses onto the typed error hierarchy."""
    if response.status_code == 401:
        raise ProviderAuthError(response.text, provider=provider)
    if response.status_code == 429:
        raise ProviderRateLimitError(response.text, provider=provider)
    if response.status_code >= 400:
        raise ProviderResponseError(response.text, provider=provider)


def json_field(response: httpx.Response, provider: str) -> dict:
    """Parse a JSON-object body, tolerating SSE-style trailing framing.

    Some OpenAI-compatible gateways append `data: [DONE]` after the JSON
    body even for non-streaming requests; json.loads rejects that. The
    first JSON value is the reply; trailing bytes are ignored.
    """
    raw = response.text
    try:
        decoder = json.JSONDecoder()
        data, _ = decoder.raw_decode(raw.lstrip())
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
    retries: int = 1,
) -> httpx.Response:
    """Run one vendor HTTP call, wrapping transport failures as ProviderErrors.

    Transport-level failures (DNS blips, dropped connections) get one
    automatic retry — the live pass caught gateways throwing transient
    ENOTFOUND mid-conversation. Non-2xx responses are NOT retried: they are
    deterministic vendor answers and raising here lets the status mapping
    classify them.
    """
    last_transport_error: httpx.HTTPError | None = None
    for attempt in range(retries + 1):
        try:
            return request()
        except httpx.HTTPError as transport_error:
            last_transport_error = transport_error
            if attempt >= retries:
                break
    assert last_transport_error is not None
    if isinstance(last_transport_error, httpx.TimeoutException):
        raise ProviderTimeoutError(
            str(last_transport_error), provider=provider
        ) from last_transport_error
    raise ProviderTimeoutError(
        f"connection failed: {last_transport_error}", provider=provider
    ) from last_transport_error
