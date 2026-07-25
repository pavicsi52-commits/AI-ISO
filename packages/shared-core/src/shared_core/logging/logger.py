"""Structured logger configuration and factory.

Per docs/014_Enterprise_Logging_Framework.md.txt "OBJECTIVE": every
microservice uses this framework. No service creates its own logger or
calls ``print()``.
"""

from __future__ import annotations

import logging
import sys
from typing import Any

from shared_core.logging.constants import LoggingFrameworkConstants
from shared_core.logging.json_formatter import JsonFormatter

_LEVEL_NAMES = frozenset({"TRACE", "DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"})

logging.addLevelName(
    LoggingFrameworkConstants.TRACE_LEVEL_NUM, LoggingFrameworkConstants.TRACE_LEVEL_NAME
)


class AIIOSLogger(logging.Logger):
    """The logger every AI-IOS component uses (docs/014 "LOGGER API").

    Extends the standard library ``Logger`` with the four framework-specific
    methods the spec requires beyond the six standard levels: ``trace()``
    (a custom level below ``DEBUG``) and three *category* methods --
    ``audit()``, ``security()``, ``performance()`` -- that log at an
    appropriate standard level while tagging the record with a ``category``
    field, so audit/security/performance events are filterable downstream
    (e.g. in OpenSearch) without inventing three more severity levels the
    spec doesn't ask for.
    """

    def trace(self, message: str, *args: Any, **kwargs: Any) -> None:
        """Log at ``TRACE``, the most verbose level (below ``DEBUG``)."""
        if self.isEnabledFor(LoggingFrameworkConstants.TRACE_LEVEL_NUM):
            self._log(LoggingFrameworkConstants.TRACE_LEVEL_NUM, message, args, **kwargs)

    def audit(
        self,
        action: str,
        *,
        actor_id: str | None = None,
        resource: str | None = None,
        outcome: str = "success",
        **fields: Any,
    ) -> None:
        """Log an audit event: authN/authZ, config changes, CRUD, secret access, ..."""
        self.info(
            action,
            extra={
                "extra_fields": {
                    "category": LoggingFrameworkConstants.AUDIT_CATEGORY,
                    "action": action,
                    "actor_id": actor_id,
                    "resource": resource,
                    "outcome": outcome,
                    **fields,
                }
            },
        )

    def security(
        self,
        event: str,
        *,
        outcome: str = "observed",
        **fields: Any,
    ) -> None:
        """Log a security event: failed login, permission denied, rate limit, ..."""
        self.warning(
            event,
            extra={
                "extra_fields": {
                    "category": LoggingFrameworkConstants.SECURITY_CATEGORY,
                    "event": event,
                    "outcome": outcome,
                    **fields,
                }
            },
        )

    def performance(
        self,
        metric: str,
        *,
        value: float,
        unit: str = "ms",
        **fields: Any,
    ) -> None:
        """Log a performance measurement: slow query/API/job, resource usage, ..."""
        self.info(
            metric,
            extra={
                "extra_fields": {
                    "category": LoggingFrameworkConstants.PERFORMANCE_CATEGORY,
                    "metric": metric,
                    "value": value,
                    "unit": unit,
                    **fields,
                }
            },
        )


# Every logger created via `get_logger()` (the only sanctioned entrypoint)
# must be an `AIIOSLogger`. Set at import time, not inside `configure_logging()`,
# so it's in force regardless of call order.
logging.setLoggerClass(AIIOSLogger)

_LEVEL_MAP: dict[str, int] = {
    "TRACE": LoggingFrameworkConstants.TRACE_LEVEL_NUM,
    "DEBUG": logging.DEBUG,
    "INFO": logging.INFO,
    "WARNING": logging.WARNING,
    "ERROR": logging.ERROR,
    "CRITICAL": logging.CRITICAL,
}


def resolve_log_level(level: str) -> int:
    """Map a framework log level name (including ``TRACE``) to its numeric value.

    Falls back to ``INFO`` for an unrecognized name.
    """
    return _LEVEL_MAP.get(level.upper(), logging.INFO)


def configure_logging(*, service: str, environment: str, level: str = "INFO") -> None:
    """Configure the root logger to emit structured JSON to stdout.

    Every AI-IOS service calls this once at startup (directly, or via the
    fuller :func:`shared_core.logging.factory.configure_logging_from_settings`).
    No service may configure its own logging handlers or call ``print()``.
    """
    resolved_level = resolve_log_level(level)

    root_logger = logging.getLogger()
    for existing in root_logger.handlers[:]:
        existing.close()
        root_logger.removeHandler(existing)

    handler = logging.StreamHandler(stream=sys.stdout)
    handler.setFormatter(JsonFormatter(service=service, environment=environment))
    root_logger.addHandler(handler)
    root_logger.setLevel(resolved_level)


def get_logger(name: str) -> AIIOSLogger:
    """Return a module-scoped logger that emits through the JSON formatter.

    ``setLoggerClass`` only governs loggers created *after* it runs; a
    logger with this name created earlier by other code (e.g. a
    third-party library that imported ``logging`` before AI-IOS did) would
    otherwise keep its original plain ``Logger`` class forever. Upgrading
    ``__class__`` in place is the standard workaround (structlog and others
    do the same) and is safe here since ``AIIOSLogger`` adds no ``__slots__``
    or new instance layout.
    """
    logger = logging.getLogger(name)
    if not isinstance(logger, AIIOSLogger):
        logger.__class__ = AIIOSLogger
    return logger  # type: ignore[return-value]
