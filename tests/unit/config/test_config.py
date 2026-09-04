"""T1.3 — env config, validation, and the provider factory/registry."""

import pytest
from pydantic import ValidationError

from config import (
    ANSWER_MAPPINGS,
    OCR_PROVIDER_NAMES,
    REASONING_PROVIDER_NAMES,
    FakeOCRProvider,
    FakeReasoningProvider,
    Settings,
    build_ocr_provider,
    build_reasoning_provider,
)
from core.domain.ports import OCRProvider, ReasoningProvider


def test_defaults_retry_cap_2_noise_rate_0_05_answer_mapping_trust_model() -> None:
    settings = Settings(_env_file=None)
    assert settings.retry_cap == 2
    assert settings.noise_rate == 0.05
    assert settings.answer_mapping == "trust_model"
    assert settings.results_dir.endswith("results")


def test_unknown_ocr_provider_raises_clear_error(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OCR_PROVIDER", "wat")
    with pytest.raises(ValidationError) as err:
        Settings(_env_file=None)
    message = str(err.value)
    assert "wat" in message
    for name in OCR_PROVIDER_NAMES:
        assert name in message


def test_unknown_reasoning_provider_raises_clear_error(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("REASONING_PROVIDER", "wat")
    with pytest.raises(ValidationError) as err:
        Settings(_env_file=None)
    message = str(err.value)
    for name in REASONING_PROVIDER_NAMES:
        assert name in message


def test_invalid_answer_mapping_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ANSWER_MAPPING", "trust_no_one")
    with pytest.raises(ValidationError):
        Settings(_env_file=None)
    assert "trust_model" in ANSWER_MAPPINGS
    assert "labels_then_position" in ANSWER_MAPPINGS


def test_invalid_noise_rate_out_of_range_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("NOISE_RATE", "1.5")
    with pytest.raises(ValidationError):
        Settings(_env_file=None)
    monkeypatch.setenv("NOISE_RATE", "-0.1")
    with pytest.raises(ValidationError):
        Settings(_env_file=None)


def test_unknown_log_level_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LOG_LEVEL", "WAT")
    with pytest.raises(ValidationError):
        Settings(_env_file=None)


@pytest.fixture
def restore_root_logging():
    """configure_logging mutates the global root logger (force=True); restore
    it so the mutation never leaks into other tests."""
    import logging

    root = logging.getLogger()
    saved_handlers = root.handlers[:]
    saved_level = root.level
    yield
    root.handlers[:] = saved_handlers
    root.setLevel(saved_level)


def test_configure_logging_sets_the_datic_level(restore_root_logging) -> None:
    import logging

    from config import configure_logging

    configure_logging("WARNING")
    assert logging.getLogger().isEnabledFor(logging.WARNING)
    assert not logging.getLogger("core.services.retry_loop").isEnabledFor(logging.INFO)
    configure_logging("INFO")
    assert logging.getLogger("core.services.retry_loop").isEnabledFor(logging.INFO)


def test_configure_logging_writes_the_trail_to_log_file(restore_root_logging, tmp_path) -> None:
    import logging

    from config import configure_logging

    log_file = tmp_path / "audit.log"
    configure_logging("INFO", log_file=str(log_file))
    logging.getLogger("core.services.retry_loop").info("trail entry")
    for handler in root_handlers():
        handler.flush()
    assert "trail entry" in log_file.read_text(encoding="utf-8")


def root_handlers() -> list:
    import logging

    return logging.getLogger().handlers


def test_env_overrides_loaded(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("RETRY_CAP", "3")
    monkeypatch.setenv("NOISE_RATE", "0.1")
    monkeypatch.setenv("ANSWER_MAPPING", "labels_then_position")
    monkeypatch.setenv("OCR_PROVIDER", "fake")
    monkeypatch.setenv("REASONING_PROVIDER", "fake")
    settings = Settings(_env_file=None)
    assert settings.retry_cap == 3
    assert settings.noise_rate == 0.1
    assert settings.answer_mapping == "labels_then_position"


def test_factory_builds_each_registered_provider() -> None:
    from config import OCR_PROVIDER_REGISTRY, REASONING_PROVIDER_REGISTRY

    for name in OCR_PROVIDER_REGISTRY:
        settings = Settings(_env_file=None, ocr_provider=name)
        assert isinstance(build_ocr_provider(name, settings), OCRProvider)
    for name in REASONING_PROVIDER_REGISTRY:
        settings = Settings(_env_file=None, reasoning_provider=name)
        assert isinstance(build_reasoning_provider(name, settings), ReasoningProvider)


def test_factory_builds_the_fake_provider() -> None:
    settings = Settings(_env_file=None, ocr_provider="fake", reasoning_provider="fake")
    assert isinstance(build_ocr_provider("fake", settings), FakeOCRProvider)
    assert isinstance(build_reasoning_provider("fake", settings), FakeReasoningProvider)


def test_registry_keys_are_valid_provider_names() -> None:
    from config import OCR_PROVIDER_REGISTRY, REASONING_PROVIDER_REGISTRY

    assert set(OCR_PROVIDER_REGISTRY) <= set(OCR_PROVIDER_NAMES)
    assert set(REASONING_PROVIDER_REGISTRY) <= set(REASONING_PROVIDER_NAMES)
    assert set(ANSWER_MAPPINGS) == {"trust_model", "labels_then_position"}


def test_factory_error_message_lists_valid_names() -> None:
    from config import OCR_PROVIDER_REGISTRY, REASONING_PROVIDER_REGISTRY

    settings = Settings(_env_file=None)
    with pytest.raises(ValueError) as err:
        build_ocr_provider("wat", settings)
    for name in OCR_PROVIDER_REGISTRY:
        assert name in str(err.value)
    with pytest.raises(ValueError) as err:
        build_reasoning_provider("wat", settings)
    for name in REASONING_PROVIDER_REGISTRY:
        assert name in str(err.value)
