"""Structured log record field collection.

Builds the full field set docs/014_Enterprise_Logging_Framework.md.txt
"LOG FORMAT" requires on every record. Kept separate from
:mod:`shared_core.logging.json_formatter` so the field-collection logic
(what goes into a record) is independent of how it's serialized.
"""

from __future__ import annotations

import logging
import os
import socket
import threading
from datetime import UTC, datetime
from typing import Any

from shared_core.logging.context import get_log_context
from shared_core.logging.request_context import get_request_log_context

_HOSTNAME = socket.gethostname()
_EXCEPTION_FORMATTER = logging.Formatter()


def _current_trace_context() -> tuple[str | None, str | None]:
    """Best-effort OpenTelemetry trace/span IDs for the currently active span."""
    try:
        from opentelemetry import trace  # noqa: PLC0415 -- optional, guarded by ImportError
    except ImportError:
        return None, None

    span_context = trace.get_current_span().get_span_context()
    if not span_context.is_valid:
        return None, None
    return format(span_context.trace_id, "032x"), format(span_context.span_id, "016x")


def build_log_record(
    record: logging.LogRecord, *, service: str, environment: str
) -> dict[str, Any]:
    """Build the full structured-logging field set for *record*.

    Pulls identity/correlation fields from :mod:`shared_core.logging.context`,
    HTTP fields from :mod:`shared_core.logging.request_context`, trace/span
    IDs from the active OpenTelemetry span (if any), and process/thread/host
    identifiers directly -- every field
    docs/014_Enterprise_Logging_Framework.md.txt "LOG FORMAT" requires.
    """
    context = get_log_context()
    request_context = get_request_log_context()
    trace_id, span_id = _current_trace_context()

    payload: dict[str, Any] = {
        "timestamp": datetime.now(UTC).isoformat(),
        "level": record.levelname,
        "service": service,
        "environment": environment,
        "hostname": _HOSTNAME,
        "request_id": context.request_id,
        "correlation_id": context.correlation_id,
        "organization_id": context.organization_id,
        "project_id": context.project_id,
        "user_id": context.user_id,
        "session_id": context.session_id,
        "trace_id": context.trace_id or trace_id,
        "span_id": context.span_id or span_id,
        "thread_id": threading.get_ident(),
        "process_id": os.getpid(),
        "method": request_context.method,
        "url": request_context.url,
        "status_code": None,
        "latency_ms": None,
        "ip_address": request_context.ip_address,
        "user_agent": request_context.user_agent,
        "message": record.getMessage(),
        "exception": None,
        "logger": record.name,
    }

    extra_fields = getattr(record, "extra_fields", None)
    if extra_fields:
        payload.update(extra_fields)

    if record.exc_info:
        payload["exception"] = _EXCEPTION_FORMATTER.formatException(record.exc_info)

    return payload
