"""Log output handler factories.

Per docs/014_Enterprise_Logging_Framework.md.txt "LOG OUTPUTS": console,
file (rotated -- see :mod:`shared_core.logging.rotation`), and
OpenTelemetry. Kafka, Cloud Logging, and Elastic are explicitly future
work, not implemented here.
"""

from __future__ import annotations

import logging
import sys
import warnings
from pathlib import Path

from shared_core.logging.constants import LoggingFrameworkConstants
from shared_core.logging.exceptions import LogHandlerError
from shared_core.logging.json_formatter import JsonFormatter
from shared_core.logging.rotation import SizeAndTimeRotatingHandler


def build_console_handler(*, service: str, environment: str) -> logging.Handler:
    """Build a handler that writes structured JSON to stdout."""
    handler = logging.StreamHandler(stream=sys.stdout)
    handler.setFormatter(JsonFormatter(service=service, environment=environment))
    return handler


def build_file_handler(
    *,
    service: str,
    environment: str,
    file_path: str,
    max_bytes: int = LoggingFrameworkConstants.DEFAULT_MAX_BYTES,
    rotation_when: str = LoggingFrameworkConstants.DEFAULT_ROTATION_WHEN,
    backup_count: int = LoggingFrameworkConstants.DEFAULT_BACKUP_COUNT,
    compress: bool = True,
) -> logging.Handler:
    """Build a handler that writes structured JSON to a daily- and size-rotated file.

    Raises:
        LogHandlerError: If the log file's directory can't be created or
            the file can't be opened for writing.
    """
    path = Path(file_path)
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        handler = SizeAndTimeRotatingHandler(
            str(path),
            when=rotation_when,
            backup_count=backup_count,
            max_bytes=max_bytes,
            compress=compress,
        )
    except OSError as exc:
        raise LogHandlerError(f"Could not open log file '{file_path}': {exc}") from exc
    handler.setFormatter(JsonFormatter(service=service, environment=environment))
    return handler


def build_otel_handler(*, service_name: str, level: int = logging.NOTSET) -> logging.Handler:
    """Build a handler bridging stdlib logging into an OpenTelemetry ``LoggerProvider``.

    Uses a console log exporter by default (no OTLP collector in the
    infrastructure stack yet), mirroring
    :func:`shared_core.telemetry.provider.configure_tracing`.

    Raises:
        LogHandlerError: If the OpenTelemetry logs SDK isn't available.
    """
    try:
        from opentelemetry.sdk._logs import LoggerProvider, LoggingHandler  # noqa: PLC0415
        from opentelemetry.sdk._logs.export import (  # noqa: PLC0415
            ConsoleLogRecordExporter,
            SimpleLogRecordProcessor,
        )
        from opentelemetry.sdk.resources import SERVICE_NAME, Resource  # noqa: PLC0415
    except ImportError as exc:
        raise LogHandlerError("OpenTelemetry logs SDK is not installed.") from exc

    resource = Resource.create({SERVICE_NAME: service_name})
    provider = LoggerProvider(resource=resource)
    provider.add_log_record_processor(SimpleLogRecordProcessor(ConsoleLogRecordExporter()))
    with warnings.catch_warnings():
        # `LoggingHandler` is soft-deprecated in favor of the separate
        # `opentelemetry-instrumentation-logging` package, which isn't (and
        # shouldn't need to be) a dependency here -- it's an auto-instrumentation
        # framework, not a drop-in replacement. The SDK-native handler is
        # still shipped and fully functional; this only silences the warning.
        warnings.simplefilter("ignore", DeprecationWarning)
        return LoggingHandler(level=level, logger_provider=provider)
