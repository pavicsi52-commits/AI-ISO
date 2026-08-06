"""Webhook service telemetry (docs/057 "TELEMETRY"): reception, signature
verification, transformation, queue processing, delivery, retry, replay.

Integrates ``shared_core.telemetry`` (Prompt 024).

**Every call below passes attributes via ``**{...}``, never a literal
``attributes={...}`` keyword.** ``start_span``'s own signature is
``start_span(tracer, name, *, span_type=None, **attributes)`` -- there is
no parameter actually named ``attributes``, only that catch-all. Passing
one anyway silently drops every attribute onto the floor instead of
raising -- a confirmed, repo-wide defect in every AI-IOS service after
``authentication-service``. This copy was written correct from the start.

**Spans carry identifiers and outcomes, never payload content.** A
webhook's own body may carry another tenant's sensitive data; a tracing
backend has different retention and different access rules than this
service's own database does.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager

from opentelemetry.trace import Span, Tracer
from shared_core.telemetry.span import SpanType, start_span


@contextmanager
def trace_reception(
    tracer: Tracer, *, kind: str, event_type: str, **attributes: object
) -> Iterator[Span]:
    """Span receiving one webhook or internal event."""
    with start_span(
        tracer,
        "webhook.reception",
        span_type=SpanType.REST_API,
        **{"webhook.kind": kind, "webhook.event_type": event_type, **attributes},
    ) as span:
        yield span


@contextmanager
def trace_signature_verification(
    tracer: Tracer, *, endpoint_id: str, verified: bool, **attributes: object
) -> Iterator[Span]:
    """Span verifying one inbound webhook's own HMAC signature."""
    with start_span(
        tracer,
        "webhook.signature.verify",
        span_type=SpanType.REST_API,
        **{"webhook.endpoint_id": endpoint_id, "webhook.verified": verified, **attributes},
    ) as span:
        yield span


@contextmanager
def trace_transformation(
    tracer: Tracer, *, endpoint_id: str, kind: str, **attributes: object
) -> Iterator[Span]:
    """Span applying one transformation rule to a payload."""
    with start_span(
        tracer,
        "webhook.transformation.apply",
        span_type=SpanType.BACKGROUND_JOB,
        **{"webhook.endpoint_id": endpoint_id, "webhook.transformation_kind": kind, **attributes},
    ) as span:
        yield span


@contextmanager
def trace_queue_processing(
    tracer: Tracer, *, delivery_id: str, endpoint_id: str, **attributes: object
) -> Iterator[Span]:
    """Span queueing one delivery for its endpoint."""
    with start_span(
        tracer,
        "webhook.queue.process",
        span_type=SpanType.BACKGROUND_JOB,
        **{"webhook.delivery_id": delivery_id, "webhook.endpoint_id": endpoint_id, **attributes},
    ) as span:
        yield span


@contextmanager
def trace_delivery(
    tracer: Tracer,
    *,
    delivery_id: str,
    endpoint_id: str,
    status_code: int | None,
    **attributes: object,
) -> Iterator[Span]:
    """Span one delivery attempt reaching a terminal outcome."""
    with start_span(
        tracer,
        "webhook.delivery",
        span_type=SpanType.BACKGROUND_JOB,
        **{
            "webhook.delivery_id": delivery_id,
            "webhook.endpoint_id": endpoint_id,
            "webhook.status_code": status_code,
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
        "webhook.retry",
        span_type=SpanType.BACKGROUND_JOB,
        **{
            "webhook.delivery_id": delivery_id,
            "webhook.attempt_number": attempt_number,
            **attributes,
        },
    ) as span:
        yield span


@contextmanager
def trace_replay(
    tracer: Tracer, *, job_id: str, scope: str, **attributes: object
) -> Iterator[Span]:
    """Span executing one replay job."""
    with start_span(
        tracer,
        "webhook.replay",
        span_type=SpanType.BACKGROUND_JOB,
        **{"webhook.job_id": job_id, "webhook.scope": scope, **attributes},
    ) as span:
        yield span


@contextmanager
def trace_worker_tick(
    tracer: Tracer, *, worker: str, processed: int, **attributes: object
) -> Iterator[Span]:
    """Span one background worker's sweep tick."""
    with start_span(
        tracer,
        "webhook.worker.tick",
        span_type=SpanType.BACKGROUND_JOB,
        **{"webhook.worker": worker, "webhook.processed": processed, **attributes},
    ) as span:
        yield span


@contextmanager
def trace_publish(tracer: Tracer, *, event_name: str, **attributes: object) -> Iterator[Span]:
    """Span one domain-event publish."""
    with start_span(
        tracer,
        "webhook.event.publish",
        span_type=SpanType.BACKGROUND_JOB,
        **{"webhook.event": event_name, **attributes},
    ) as span:
        yield span


__all__ = [
    "trace_delivery",
    "trace_publish",
    "trace_queue_processing",
    "trace_reception",
    "trace_replay",
    "trace_retry",
    "trace_signature_verification",
    "trace_transformation",
    "trace_worker_tick",
]
