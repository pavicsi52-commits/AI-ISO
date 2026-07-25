"""Queue Publish/Consume span helpers.

Per docs/024_Enterprise_Telemetry_Framework.md.txt "SPAN TYPES": Queue
Publish, Queue Consume. Instruments :mod:`shared_core.queue` operations
without that package needing to depend on telemetry itself -- a caller
(``QueueManager.publish``/``consume``, or a service using it) wraps its
own call with these.

Also covers "CONTEXT PROPAGATION": Queue Messages -- a message's own
header dict *is* the propagation carrier. ``trace_queue_publish``
injects the current trace context into it before the message goes out;
``trace_queue_consume`` extracts it back, so a worker's processing span
continues the publisher's trace rather than starting an unrelated one
(also covering "MIDDLEWARE": Queue Workers -- the first span a worker
creates from a message *is* that worker's root trace).
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager

from opentelemetry.trace import Span, Tracer

from shared_core.telemetry.propagation import (
    extract_context,
    inject_context,
    restore_context,
    use_context,
)
from shared_core.telemetry.span import SpanType, start_span


@contextmanager
def trace_queue_publish(
    tracer: Tracer, queue_name: str, *, headers: dict[str, str] | None = None, **attributes: str
) -> Iterator[Span]:
    """Trace a message publish to *queue_name* ("Queue Publish").

    If *headers* is given, the current trace context is injected into it
    in place, so a consumer extracting it later continues this trace.
    """
    with start_span(
        tracer,
        f"queue.publish {queue_name}",
        span_type=SpanType.QUEUE_PUBLISH,
        queue_name=queue_name,
        **attributes,
    ) as span:
        if headers is not None:
            inject_context(headers)
        yield span


@contextmanager
def trace_queue_consume(
    tracer: Tracer, queue_name: str, *, headers: dict[str, str] | None = None, **attributes: str
) -> Iterator[Span]:
    """Trace a message consume from *queue_name* ("Queue Consume").

    If *headers* is given (the consumed message's own headers), the
    publisher's trace context is extracted from it first, so this span
    -- and everything nested under it -- continues that trace instead of
    starting a new, disconnected one.
    """
    token = use_context(extract_context(headers)) if headers is not None else None
    try:
        with start_span(
            tracer,
            f"queue.consume {queue_name}",
            span_type=SpanType.QUEUE_CONSUME,
            queue_name=queue_name,
            **attributes,
        ) as span:
            yield span
    finally:
        if token is not None:
            restore_context(token)


__all__ = ["trace_queue_consume", "trace_queue_publish"]
