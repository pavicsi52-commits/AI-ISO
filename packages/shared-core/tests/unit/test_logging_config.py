"""Tests for logging configuration (sourced from the Configuration Framework)."""

from __future__ import annotations

import logging

import pytest
from shared_core.config import Environment, load_settings
from shared_core.logging.config import build_logging_config
from shared_core.logging.exceptions import LoggingConfigurationError
from shared_core.logging.factory import (
    configure_logging_from_config,
    configure_logging_from_settings,
)
from shared_core.logging.json_formatter import JsonFormatter


def test_build_logging_config_maps_every_field() -> None:
    settings = load_settings(
        log_level="DEBUG",
        log_outputs="console,file",
        log_file_path="logs/custom.log",
        log_file_max_bytes=12345,
        log_rotation_when="H",
        log_backup_count=7,
        log_compress_rotated=False,
        log_retention_days=30,
        log_mask_enabled=False,
    )

    config = build_logging_config(settings)

    assert config.service == settings.application.app_name
    assert config.environment == settings.application.environment.value
    assert config.level == "DEBUG"
    assert config.outputs == ("console", "file")
    assert config.file_path == "logs/custom.log"
    assert config.file_max_bytes == 12345
    assert config.rotation_when == "H"
    assert config.backup_count == 7
    assert config.compress_rotated is False
    assert config.retention_days == 30
    assert config.mask_enabled is False


def test_configure_logging_from_config_installs_console_handler() -> None:
    config = build_logging_config(load_settings(log_outputs="console"))

    configure_logging_from_config(config)

    root_logger = logging.getLogger()
    assert any(isinstance(h.formatter, JsonFormatter) for h in root_logger.handlers)


def test_configure_logging_from_config_rejects_unsupported_output() -> None:
    config = build_logging_config(load_settings(log_outputs="console,carrier-pigeon"))

    with pytest.raises(LoggingConfigurationError):
        configure_logging_from_config(config)


def test_configure_logging_from_settings_end_to_end() -> None:
    settings = load_settings(environment=Environment.TESTING, log_level="WARNING")

    configure_logging_from_settings(settings)

    assert logging.getLogger().level == logging.WARNING


def test_configure_logging_from_config_installs_file_handler(tmp_path) -> None:
    config = build_logging_config(
        load_settings(log_outputs="file", log_file_path=str(tmp_path / "app.log"))
    )

    configure_logging_from_config(config)

    root_logger = logging.getLogger()
    assert any(isinstance(h.formatter, JsonFormatter) for h in root_logger.handlers)


def test_configure_logging_from_config_installs_otel_handler() -> None:
    config = build_logging_config(load_settings(log_outputs="otel"))

    configure_logging_from_config(config)

    root_logger = logging.getLogger()
    assert len(root_logger.handlers) == 1


def test_configure_logging_from_config_skips_masking_filter_when_disabled() -> None:
    config = build_logging_config(load_settings(log_outputs="console", log_mask_enabled=False))

    configure_logging_from_config(config)

    root_logger = logging.getLogger()
    assert root_logger.handlers[0].filters == []
