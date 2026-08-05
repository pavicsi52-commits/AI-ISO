"""Notification center telemetry (docs/055 "TELEMETRY"): template rendering,
queue processing, delivery, retries, acknowledgements, API calls.

Integrates ``shared_core.telemetry`` (Prompt 024).

No dedicated :class:`~shared_core.telemetry.span.SpanType` member exists
for notification work, so each span falls back to ``REST_API`` or
``BACKGROUND_JOB`` with a distinguishing name -- the same choice every
prior AI-IOS service made for the same reason.

**Every call below passes attributes via ``**{...}``, never a literal
``attributes={...}`` keyword.** ``start_span``'s own signature is
``start_span(tracer, name, *, span_type=None, **attributes)`` -- there is
no parameter actually named ``attributes``, only that catch-all. Passing
one anyway silently drops every attribute onto the floor instead of
raising -- a confirmed, repo-wide defect in every AI-IOS service after
``authentication-service`` (first documented in
``services/change-management-service``'s own copy of this file). This
copy was written correct from the start, using ``**{...}`` unpacking
throughout.

**Spans carry identifiers, channels, and statuses, never notification
content.** A notification's own ``body``/``subject`` can carry
sensitive, recipient-specific data; a tracing backend has different
retention and different access rules than this service's own database
does.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager

from opentelemetry.trace import Span, Tracer
from shared_core.telemetry.span import SpanType, start_span


@contextmanager
def trace_template_rendering(
    tracer: Tracer, *, template_key: str, template_format: str, **attributes: object
) -> Iterator[Span]:
    """Span rendering one template against its variables."""
    with start_span(
        tracer,
        "notification.template.render",
        span_type=SpanType.BACKGROUND_JOB,
        **{
            "notification.template_key": template_key,
            "notification.template_format": template_format,
            **attributes,
        },
    ) as span:
        yield span


@contextmanager
def trace_queue_processing(
    tracer: Tracer, *, notification_id: str, channel: str, **attributes: object
) -> Iterator[Span]:
    """Span queueing one notification's delivery over one channel."""
    with start_span(
        tracer,
        "notification.queue.process",
        span_type=SpanType.BACKGROUND_JOB,
        **{
            "notification.notification_id": notification_id,
            "notification.channel": channel,
            **attributes,
        },
    ) as span:
        yield span


@contextmanager
def trace_delivery(
    tracer: Tracer, *, delivery_id: str, channel: str, status: str, **attributes: object
) -> Iterator[Span]:
    """Span one delivery attempt reaching a terminal outcome."""
    with start_span(
        tracer,
        "notification.delivery",
        span_type=SpanType.BACKGROUND_JOB,
        **{
            "notification.delivery_id": delivery_id,
            "notification.channel": channel,
            "notification.status": status,
            **attributes,
        },
    ) as span:
        yield span


@contextmanager
def trace_retry(
    tracer: Tracer, *, delivery_id: str, attempt_number: int, **attributes: object
) -> Iterator[Span]:
    """Span dispatching one retry attempt."""
    with start_span(
        tracer,
        "notification.retry",
        span_type=SpanType.BACKGROUND_JOB,
        **{
            "notification.delivery_id": delivery_id,
            "notification.attempt_number": attempt_number,
            **attributes,
        },
    ) as span:
        yield span


@contextmanager
def trace_acknowledgement(
    tracer: Tracer, *, notification_id: str, **attributes: object
) -> Iterator[Span]:
    """Span a recipient acknowledging a notification."""
    with start_span(
        tracer,
        "notification.acknowledge",
        span_type=SpanType.REST_API,
        **{"notification.notification_id": notification_id, **attributes},
    ) as span:
        yield span


@contextmanager
def trace_api_call(tracer: Tracer, *, route: str, **attributes: object) -> Iterator[Span]:
    """Span one notable API call this service's own routes made outward.

    Distinct from the automatic per-request server-side spans
    ``Instrumentator``/``RequestContextMiddleware`` already emit for
    every inbound HTTP request -- this is for a route's own outbound
    call it wants named and attributed on its own terms (e.g. a webhook
    delivery attempt), not a duplicate of the inbound span.
    """
    with start_span(
        tracer,
        "notification.api.call",
        span_type=SpanType.REST_API,
        **{"notification.route": route, **attributes},
    ) as span:
        yield span


@contextmanager
def trace_worker_tick(
    tracer: Tracer, *, worker: str, processed: int, **attributes: object
) -> Iterator[Span]:
    """Span one background worker's sweep tick."""
    with start_span(
        tracer,
        "notification.worker.tick",
        span_type=SpanType.BACKGROUND_JOB,
        **{"notification.worker": worker, "notification.processed": processed, **attributes},
    ) as span:
        yield span


@contextmanager
def trace_publish(tracer: Tracer, *, event_name: str, **attributes: object) -> Iterator[Span]:
    """Span one domain-event publish."""
    with start_span(
        tracer,
        "notification.event.publish",
        span_type=SpanType.BACKGROUND_JOB,
        **{"notification.event": event_name, **attributes},
    ) as span:
        yield span


__all__ = [
    "trace_acknowledgement",
    "trace_api_call",
    "trace_delivery",
    "trace_publish",
    "trace_queue_processing",
    "trace_retry",
    "trace_template_rendering",
    "trace_worker_tick",
]
