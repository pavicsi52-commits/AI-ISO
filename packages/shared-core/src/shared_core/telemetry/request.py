"""Request ID correlation.

Per docs/024_Enterprise_Telemetry_Framework.md.txt "OBJECTIVE": Request
IDs. Request/correlation ID *generation* already happens in
:class:`shared_core.middleware.request_context.RequestContextMiddleware`
(Prompt 012); this module attaches those already-assigned identifiers
onto the current trace span, so a trace can be looked up by the same
request ID a client sees in its ``X-Request-ID`` response header.
"""

from __future__ import annotations

from opentelemetry.trace import Span

from shared_core.logging.context import get_log_context


def tag_span_with_request_ids(span: Span) -> None:
    """Attach the current request/correlation IDs to *span*, if any are bound.

    A no-op for whichever ID isn't currently bound (e.g. a background
    job's span, which has no HTTP request behind it).
    """
    context = get_log_context()
    if context.request_id is not None:
        span.set_attribute("request_id", context.request_id)
    if context.correlation_id is not None:
        span.set_attribute("correlation_id", context.correlation_id)


def current_request_id() -> str | None:
    """The current request ID, if any is bound."""
    return get_log_context().request_id


def current_correlation_id() -> str | None:
    """The current correlation ID, if any is bound."""
    return get_log_context().correlation_id


__all__ = ["current_correlation_id", "current_request_id", "tag_span_with_request_ids"]
