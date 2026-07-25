"""Trace context.

Per docs/024_Enterprise_Telemetry_Framework.md.txt "TRACE CONTEXT": every
trace shall carry trace_id/span_id/parent_span_id/correlation_id/
request_id/organization_id/project_id/user_id/tenant_id/service_name/
service_version/environment/hostname/timestamp.

Deliberately not a second, parallel context store: identity/correlation
fields (request_id/correlation_id/organization_id/project_id/user_id)
already live in :mod:`shared_core.logging.context`'s ``LogContext``,
populated by ``shared_core.middleware`` -- this module reads that
context rather than duplicating it, and adds only what's genuinely new
here (trace/span identifiers from the active OpenTelemetry span, plus
service/host identity).
"""

from __future__ import annotations

import socket
from dataclasses import dataclass
from datetime import UTC, datetime

from opentelemetry import trace

from shared_core.logging.context import get_log_context

_HOSTNAME = socket.gethostname()


@dataclass(frozen=True, slots=True)
class TraceContext:
    """The full set of identifiers docs/024 "TRACE CONTEXT" requires."""

    trace_id: str | None
    span_id: str | None
    parent_span_id: str | None
    correlation_id: str | None
    request_id: str | None
    organization_id: str | None
    project_id: str | None
    user_id: str | None
    tenant_id: str | None
    service_name: str
    service_version: str
    environment: str
    hostname: str
    timestamp: datetime


def current_span_ids() -> tuple[str | None, str | None, str | None]:
    """Return ``(trace_id, span_id, parent_span_id)`` for the active OpenTelemetry span.

    All three are ``None`` if there is no active, valid span (e.g. no
    root trace has been started yet). ``parent_span_id`` is best-effort:
    the OpenTelemetry API doesn't expose the current span's parent
    directly, so it's only available immediately after :func:`shared_core
    .telemetry.span.start_span` records it explicitly.
    """
    span_context = trace.get_current_span().get_span_context()
    if not span_context.is_valid:
        return None, None, None
    return format(span_context.trace_id, "032x"), format(span_context.span_id, "016x"), None


def current_trace_context(
    *,
    service_name: str,
    service_version: str,
    environment: str,
    tenant_id: str | None = None,
) -> TraceContext:
    """Build the current :class:`TraceContext` from the active span and log context."""
    trace_id, span_id, parent_span_id = current_span_ids()
    log_context = get_log_context()
    return TraceContext(
        trace_id=log_context.trace_id or trace_id,
        span_id=log_context.span_id or span_id,
        parent_span_id=parent_span_id,
        correlation_id=log_context.correlation_id,
        request_id=log_context.request_id,
        organization_id=log_context.organization_id,
        project_id=log_context.project_id,
        user_id=log_context.user_id,
        tenant_id=tenant_id,
        service_name=service_name,
        service_version=service_version,
        environment=environment,
        hostname=_HOSTNAME,
        timestamp=datetime.now(UTC),
    )


__all__ = ["TraceContext", "current_span_ids", "current_trace_context"]
