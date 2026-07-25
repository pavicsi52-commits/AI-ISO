"""Logging-module-local constants.

Distinct from :class:`shared_core.constants.logging.LoggingConstants`
(domain-wide defaults shared across subpackages) -- these govern the
logging framework's own mechanics: the custom TRACE level, output names,
and rotation defaults.
"""

from __future__ import annotations

from typing import Final


class LoggingFrameworkConstants:
    """Constants governing log levels, outputs, and rotation."""

    TRACE_LEVEL_NUM: Final[int] = 5
    TRACE_LEVEL_NAME: Final[str] = "TRACE"

    CONSOLE_OUTPUT: Final[str] = "console"
    FILE_OUTPUT: Final[str] = "file"
    OTEL_OUTPUT: Final[str] = "otel"
    SUPPORTED_OUTPUTS: Final[frozenset[str]] = frozenset({"console", "file", "otel"})

    AUDIT_CATEGORY: Final[str] = "audit"
    SECURITY_CATEGORY: Final[str] = "security"
    PERFORMANCE_CATEGORY: Final[str] = "performance"

    DEFAULT_ROTATION_WHEN: Final[str] = "midnight"
    DEFAULT_BACKUP_COUNT: Final[int] = 30
    DEFAULT_MAX_BYTES: Final[int] = 100_000_000
    DEFAULT_RETENTION_DAYS: Final[int] = 90
    ROTATED_FILE_SUFFIX: Final[str] = ".gz"
