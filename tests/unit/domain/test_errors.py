"""T1.2 — typed error hierarchy and port contracts."""

import pickle
from copy import deepcopy

from core.domain.errors import (
    DaticError,
    NoiseError,
    ParseError,
    ProviderAuthError,
    ProviderError,
    ProviderRateLimitError,
    ProviderResponseError,
    ProviderTimeoutError,
)


def test_provider_errors_form_hierarchy_under_datic_error() -> None:
    for exc_type in (ProviderError, ParseError, NoiseError):
        assert issubclass(exc_type, DaticError)
    for exc_type in (
        ProviderAuthError,
        ProviderRateLimitError,
        ProviderResponseError,
        ProviderTimeoutError,
    ):
        assert issubclass(exc_type, ProviderError)


def test_timeout_and_auth_and_rate_limit_are_provider_errors() -> None:
    errors = [ProviderTimeoutError("t"), ProviderAuthError("a"), ProviderRateLimitError("r")]
    assert all(isinstance(e, ProviderError) for e in errors)
    assert all(str(e) for e in errors)


def test_parse_error_carries_raw_text_snippet() -> None:
    error = ParseError("no options found", raw_text="…truncated ocr text…")
    assert error.raw_text == "…truncated ocr text…"
    assert "no options found" in str(error)


def test_provider_errors_round_trip_through_pickle_and_deepcopy() -> None:
    for error in (
        ProviderAuthError("bad key", provider="nanonets"),
        ProviderTimeoutError("boom"),
    ):
        restored = pickle.loads(pickle.dumps(error))
        assert isinstance(restored, type(error))
        assert str(restored) == str(error)
        assert deepcopy(error).message == error.message
