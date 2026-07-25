"""Logging configuration, sourced from the Configuration Framework.

Per docs/014_Enterprise_Logging_Framework.md.txt "CONFIGURATION": log
level, output, rotation, retention, and masking are all loaded from
:mod:`shared_core.config`, never hardcoded or read from the environment
directly by this package.

This module accepts an already-loaded ``Settings`` instance rather than
importing :mod:`shared_core.config` itself: the Configuration Framework's
own internal logging already depends on :mod:`shared_core.logging`
(``shared_core.config.loader`` calls ``get_logger``), so importing back
here would form a package import cycle. The ``Settings`` type is imported
only under ``TYPE_CHECKING`` -- purely for the type hint, never at runtime.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from shared_core.config import Settings


@dataclass(frozen=True, slots=True)
class LoggingConfig:
    """Fully-resolved logging configuration for one process."""

    service: str
    environment: str
    level: str
    outputs: tuple[str, ...]
    file_path: str
    file_max_bytes: int
    rotation_when: str
    backup_count: int
    compress_rotated: bool
    retention_days: int
    mask_enabled: bool


def build_logging_config(settings: Settings) -> LoggingConfig:
    """Build a :class:`LoggingConfig` from an already-loaded
    :class:`~shared_core.config.Settings`.
    """
    return LoggingConfig(
        service=settings.application.app_name,
        environment=settings.application.environment.value,
        level=settings.logging.log_level,
        outputs=tuple(settings.logging.outputs),
        file_path=settings.logging.log_file_path,
        file_max_bytes=settings.logging.log_file_max_bytes,
        rotation_when=settings.logging.log_rotation_when,
        backup_count=settings.logging.log_backup_count,
        compress_rotated=settings.logging.log_compress_rotated,
        retention_days=settings.logging.log_retention_days,
        mask_enabled=settings.logging.log_mask_enabled,
    )
