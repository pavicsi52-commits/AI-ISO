"""Logging framework entrypoint: wires configuration into handlers.

The function every AI-IOS service calls at startup, once configuration is
loaded, in place of :func:`shared_core.logging.logger.configure_logging`
(docs/014_Enterprise_Logging_Framework.md.txt "OBJECTIVE": every service
uses this framework, none configures its own handlers).
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from shared_core.logging.config import LoggingConfig, build_logging_config
from shared_core.logging.constants import LoggingFrameworkConstants
from shared_core.logging.exceptions import LoggingConfigurationError
from shared_core.logging.filters import SensitiveDataFilter
from shared_core.logging.handlers import (
    build_console_handler,
    build_file_handler,
    build_otel_handler,
)
from shared_core.logging.logger import resolve_log_level

if TYPE_CHECKING:
    from shared_core.config import Settings


def configure_logging_from_settings(settings: Settings) -> None:
    """Configure the root logger from the Configuration Framework's ``LoggingSettings``."""
    configure_logging_from_config(build_logging_config(settings))


def configure_logging_from_config(config: LoggingConfig) -> None:
    """Configure the root logger from an already-built :class:`LoggingConfig`.

    Raises:
        LoggingConfigurationError: If an unsupported output name is configured.
    """
    unknown_outputs = set(config.outputs) - LoggingFrameworkConstants.SUPPORTED_OUTPUTS
    if unknown_outputs:
        raise LoggingConfigurationError(
            f"Unsupported log output(s): {sorted(unknown_outputs)}",
            details=sorted(unknown_outputs),
        )

    root_logger = logging.getLogger()
    for handler in root_logger.handlers[:]:
        handler.close()
        root_logger.removeHandler(handler)

    for output in config.outputs:
        handler = _build_handler(output, config)
        if config.mask_enabled:
            handler.addFilter(SensitiveDataFilter())
        root_logger.addHandler(handler)

    root_logger.setLevel(resolve_log_level(config.level))


def _build_handler(output: str, config: LoggingConfig) -> logging.Handler:
    if output == LoggingFrameworkConstants.FILE_OUTPUT:
        return build_file_handler(
            service=config.service,
            environment=config.environment,
            file_path=config.file_path,
            max_bytes=config.file_max_bytes,
            rotation_when=config.rotation_when,
            backup_count=config.backup_count,
            compress=config.compress_rotated,
        )
    if output == LoggingFrameworkConstants.OTEL_OUTPUT:
        return build_otel_handler(service_name=config.service)
    return build_console_handler(service=config.service, environment=config.environment)
