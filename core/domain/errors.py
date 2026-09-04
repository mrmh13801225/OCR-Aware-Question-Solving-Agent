"""Typed errors: every failure in the pipeline is one of these, nothing generic."""


class DaticError(Exception):
    """Base for all pipeline errors."""


class ParseError(DaticError):
    """Raw OCR text could not be split into a question and its options."""

    def __init__(self, message: str, raw_text: str) -> None:
        super().__init__(message)
        self.raw_text = raw_text


class NoiseError(DaticError):
    """The noise injector produced an invalid state."""


class ProviderError(DaticError):
    """A vendor call failed; adapters translate every vendor quirk into a subtype."""

    def __init__(self, message: str, provider: str = "") -> None:
        super().__init__(message)
        self.message = message
        self.provider = provider

    def __str__(self) -> str:
        return f"[{self.provider}] {self.message}" if self.provider else self.message


class ProviderAuthError(ProviderError):
    """401/403 — bad or missing credentials."""


class ProviderRateLimitError(ProviderError):
    """429 — quota or rate limit hit."""


class ProviderResponseError(ProviderError):
    """Non-2xx, malformed payload, or any vendor reply the contract rejects."""


class ProviderTimeoutError(ProviderError):
    """The vendor call exceeded the timeout."""


class ProviderConnectionError(ProviderError):
    """The vendor could not be reached at all — DNS, refused, dropped."""
