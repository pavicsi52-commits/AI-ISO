"""Log correlation.

Per docs/024_Enterprise_Telemetry_Framework.md.txt "LOG CORRELATION":
every log entry shall carry trace_id/span_id/correlation_id/request_id/
service/organization_id/project_id/hostname, and logs shall be
searchable using trace identifiers.

This is deliberately thin: :mod:`shared_core.logging.formatter` (Prompt
014) already reads ``trace_id``/``span_id`` from
:mod:`shared_core.logging.context`'s ``LogContext`` -- falling back to
whatever OpenTelemetry span is ambiently active -- into every structured
log record, and every other field in the list is already a
``LogContext``/log-record field too. What's genuinely new here is
*explicitly* binding a specific span's identifiers into that same
context, for the cases OpenTelemetry's ambient current-span mechanism
doesn't reach on its own (a queue consumer that extracted a propagated
context onto a span it isn't running "current" for, a background job
correlating its logs with a trace started on a different task).
"""

from __future__ import annotations

from opentelemetry.trace import Span

from shared_core.logging.context import bind_log_context
from shared_core.telemetry.helpers import format_span_id, format_trace_id


def correlate_logs_with_span(span: Span) -> None:
    """Bind *span*'s trace/span IDs into the current logging context.

    Every subsequent log record emitted in this context carries them,
    per :func:`shared_core.logging.formatter.build_log_record`. A no-op
    if *span* has no valid context (e.g. a non-recording span).
    """
    span_context = span.get_span_context()
    if not span_context.is_valid:
        return
    bind_log_context(
        trace_id=format_trace_id(span_context.trace_id),
        span_id=format_span_id(span_context.span_id),
    )


__all__ = ["correlate_logs_with_span"]
