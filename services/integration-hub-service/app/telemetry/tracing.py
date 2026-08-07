"""Integration hub telemetry (docs/058 "TELEMETRY"): connector calls,
authentication, synchronization, transformation, routing, health checks,
marketplace operations.

Integrates ``shared_core.telemetry`` (Prompt 024).

**Every call below passes attributes via ``**{...}``, never a literal
``attributes={...}`` keyword.** ``start_span``'s own signature is
``start_span(tracer, name, *, span_type=None, **attributes)`` -- there is
no parameter actually named ``attributes``, only that catch-all. Passing
one anyway silently drops every attribute onto the floor instead of
raising -- a confirmed, repo-wide defect in every AI-IOS service after
``authentication-service``. This copy was written correct from the start.

**Spans carry identifiers and outcomes, never credential or payload
content.** A connector's own config/payload may carry another tenant's
sensitive data; a tracing backend has different retention and different
access rules than this service's own database does.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager

from opentelemetry.trace import Span, Tracer
from shared_core.telemetry.span import SpanType, start_span


@contextmanager
def trace_connector_call(
    tracer: Tracer, *, connector_id: str, operation: str, **attributes: object
) -> Iterator[Span]:
    """Span one operation performed against a connector."""
    with start_span(
        tracer,
        "hub.connector.call",
        span_type=SpanType.REST_API,
        **{"hub.connector_id": connector_id, "hub.operation": operation, **attributes},
    ) as span:
        yield span


@contextmanager
def trace_authentication(
    tracer: Tracer, *, connector_id: str, auth_method: str, succeeded: bool, **attributes: object
) -> Iterator[Span]:
    """Span authenticating one connector's own credential."""
    with start_span(
        tracer,
        "hub.authentication",
        span_type=SpanType.REST_API,
        **{
            "hub.connector_id": connector_id,
            "hub.auth_method": auth_method,
            "hub.succeeded": succeeded,
            **attributes,
        },
    ) as span:
        yield span


@contextmanager
def trace_synchronization(
    tracer: Tracer, *, sync_job_id: str, connector_id: str, mode: str, **attributes: object
) -> Iterator[Span]:
    """Span one synchronization run."""
    with start_span(
        tracer,
        "hub.synchronization",
        span_type=SpanType.BACKGROUND_JOB,
        **{
            "hub.sync_job_id": sync_job_id,
            "hub.connector_id": connector_id,
            "hub.mode": mode,
            **attributes,
        },
    ) as span:
        yield span


@contextmanager
def trace_transformation(
    tracer: Tracer, *, connector_id: str, kind: str, **attributes: object
) -> Iterator[Span]:
    """Span applying one transformation rule to a payload."""
    with start_span(
        tracer,
        "hub.transformation.apply",
        span_type=SpanType.BACKGROUND_JOB,
        **{"hub.connector_id": connector_id, "hub.transformation_kind": kind, **attributes},
    ) as span:
        yield span


@contextmanager
def trace_routing(
    tracer: Tracer, *, event_type: str, destinations_matched: int, **attributes: object
) -> Iterator[Span]:
    """Span resolving one event's own routing destinations."""
    with start_span(
        tracer,
        "hub.routing.resolve",
        span_type=SpanType.BACKGROUND_JOB,
        **{
            "hub.event_type": event_type,
            "hub.destinations_matched": destinations_matched,
            **attributes,
        },
    ) as span:
        yield span


@contextmanager
def trace_health_check(
    tracer: Tracer, *, connector_id: str, status: str, **attributes: object
) -> Iterator[Span]:
    """Span one connector health probe."""
    with start_span(
        tracer,
        "hub.health.check",
        span_type=SpanType.BACKGROUND_JOB,
        **{"hub.connector_id": connector_id, "hub.status": status, **attributes},
    ) as span:
        yield span


@contextmanager
def trace_marketplace_operation(
    tracer: Tracer, *, slug: str, operation: str, **attributes: object
) -> Iterator[Span]:
    """Span one marketplace catalog operation (publish/install/rate)."""
    with start_span(
        tracer,
        "hub.marketplace.operation",
        span_type=SpanType.REST_API,
        **{"hub.slug": slug, "hub.operation": operation, **attributes},
    ) as span:
        yield span


@contextmanager
def trace_flow_run(
    tracer: Tracer, *, flow_id: str, status: str, steps_executed: int, **attributes: object
) -> Iterator[Span]:
    """Span one integration flow run."""
    with start_span(
        tracer,
        "hub.flow.run",
        span_type=SpanType.BACKGROUND_JOB,
        **{
            "hub.flow_id": flow_id,
            "hub.status": status,
            "hub.steps_executed": steps_executed,
            **attributes,
        },
    ) as span:
        yield span


@contextmanager
def trace_worker_tick(
    tracer: Tracer, *, worker: str, processed: int, **attributes: object
) -> Iterator[Span]:
    """Span one background worker's sweep tick."""
    with start_span(
        tracer,
        "hub.worker.tick",
        span_type=SpanType.BACKGROUND_JOB,
        **{"hub.worker": worker, "hub.processed": processed, **attributes},
    ) as span:
        yield span


@contextmanager
def trace_publish(tracer: Tracer, *, event_name: str, **attributes: object) -> Iterator[Span]:
    """Span one domain-event publish."""
    with start_span(
        tracer,
        "hub.event.publish",
        span_type=SpanType.BACKGROUND_JOB,
        **{"hub.event": event_name, **attributes},
    ) as span:
        yield span


__all__ = [
    "trace_authentication",
    "trace_connector_call",
    "trace_flow_run",
    "trace_health_check",
    "trace_marketplace_operation",
    "trace_publish",
    "trace_routing",
    "trace_synchronization",
    "trace_transformation",
    "trace_worker_tick",
]
