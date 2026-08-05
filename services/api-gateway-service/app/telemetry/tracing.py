"""API gateway telemetry (docs/056 "TELEMETRY"): proxied requests, routing
decisions, rate-limit/quota checks, circuit-breaker transitions, and
health probes.

Integrates ``shared_core.telemetry`` (Prompt 024).

**Every call below passes attributes via ``**{...}``, never a literal
``attributes={...}`` keyword.** ``start_span``'s own signature is
``start_span(tracer, name, *, span_type=None, **attributes)`` -- there is
no parameter actually named ``attributes``, only that catch-all. Passing
one anyway silently drops every attribute onto the floor instead of
raising -- a confirmed, repo-wide defect in every AI-IOS service after
``authentication-service``. This copy was written correct from the start.

**Spans carry route/service identifiers and outcomes, never request or
response bodies.** A proxied payload may carry another tenant's own
sensitive data; a tracing backend has different retention and different
access rules than this service's own request/response logs do.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager

from opentelemetry.trace import Span, Tracer
from shared_core.telemetry.span import SpanType, start_span


@contextmanager
def trace_proxy_request(
    tracer: Tracer, *, method: str, path: str, route_id: str, **attributes: object
) -> Iterator[Span]:
    """Span one end-to-end proxied request."""
    with start_span(
        tracer,
        "gateway.proxy.request",
        span_type=SpanType.REST_API,
        **{
            "gateway.method": method,
            "gateway.path": path,
            "gateway.route_id": route_id,
            **attributes,
        },
    ) as span:
        yield span


@contextmanager
def trace_upstream_call(
    tracer: Tracer, *, service_id: str, instance_url: str, **attributes: object
) -> Iterator[Span]:
    """Span one outbound call to a backend instance."""
    with start_span(
        tracer,
        "gateway.upstream.call",
        span_type=SpanType.REST_API,
        **{
            "gateway.service_id": service_id,
            "gateway.instance_url": instance_url,
            **attributes,
        },
    ) as span:
        yield span


@contextmanager
def trace_route_resolution(
    tracer: Tracer, *, method: str, path: str, matched: bool, **attributes: object
) -> Iterator[Span]:
    """Span resolving which route (if any) handles one request."""
    with start_span(
        tracer,
        "gateway.route.resolve",
        span_type=SpanType.BACKGROUND_JOB,
        **{
            "gateway.method": method,
            "gateway.path": path,
            "gateway.matched": matched,
            **attributes,
        },
    ) as span:
        yield span


@contextmanager
def trace_rate_limit_check(
    tracer: Tracer, *, scope: str, allowed: bool, **attributes: object
) -> Iterator[Span]:
    """Span one rate-limit decision."""
    with start_span(
        tracer,
        "gateway.ratelimit.check",
        span_type=SpanType.BACKGROUND_JOB,
        **{"gateway.scope": scope, "gateway.allowed": allowed, **attributes},
    ) as span:
        yield span


@contextmanager
def trace_quota_check(
    tracer: Tracer, *, scope: str, kind: str, allowed: bool, **attributes: object
) -> Iterator[Span]:
    """Span one quota decision."""
    with start_span(
        tracer,
        "gateway.quota.check",
        span_type=SpanType.BACKGROUND_JOB,
        **{
            "gateway.scope": scope,
            "gateway.kind": kind,
            "gateway.allowed": allowed,
            **attributes,
        },
    ) as span:
        yield span


@contextmanager
def trace_circuit_transition(
    tracer: Tracer, *, instance_url: str, from_state: str, to_state: str, **attributes: object
) -> Iterator[Span]:
    """Span a circuit breaker changing state."""
    with start_span(
        tracer,
        "gateway.circuit.transition",
        span_type=SpanType.BACKGROUND_JOB,
        **{
            "gateway.instance_url": instance_url,
            "gateway.from_state": from_state,
            "gateway.to_state": to_state,
            **attributes,
        },
    ) as span:
        yield span


@contextmanager
def trace_health_probe(
    tracer: Tracer, *, instance_url: str, status: str, **attributes: object
) -> Iterator[Span]:
    """Span one health probe of a backend instance."""
    with start_span(
        tracer,
        "gateway.health.probe",
        span_type=SpanType.BACKGROUND_JOB,
        **{"gateway.instance_url": instance_url, "gateway.status": status, **attributes},
    ) as span:
        yield span


@contextmanager
def trace_worker_tick(
    tracer: Tracer, *, worker: str, processed: int, **attributes: object
) -> Iterator[Span]:
    """Span one background worker's sweep tick."""
    with start_span(
        tracer,
        "gateway.worker.tick",
        span_type=SpanType.BACKGROUND_JOB,
        **{"gateway.worker": worker, "gateway.processed": processed, **attributes},
    ) as span:
        yield span


@contextmanager
def trace_publish(tracer: Tracer, *, event_name: str, **attributes: object) -> Iterator[Span]:
    """Span one domain-event publish."""
    with start_span(
        tracer,
        "gateway.event.publish",
        span_type=SpanType.BACKGROUND_JOB,
        **{"gateway.event": event_name, **attributes},
    ) as span:
        yield span


__all__ = [
    "trace_circuit_transition",
    "trace_health_probe",
    "trace_proxy_request",
    "trace_publish",
    "trace_quota_check",
    "trace_rate_limit_check",
    "trace_route_resolution",
    "trace_upstream_call",
    "trace_worker_tick",
]
