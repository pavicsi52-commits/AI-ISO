"""Discovery service telemetry.

Per docs/037 "TELEMETRY": Discovery Jobs, Protocol Execution,
Classification, Synchronization, Topology Updates, Inventory Updates,
Performance Metrics. "Integrate Prompt 024." No dedicated
:class:`~shared_core.telemetry.span.SpanType` member exists for any of
these, so every helper falls back to ``BACKGROUND_JOB`` (discovery jobs
run as queue-consumed background work) or ``REST_API`` (the profile/
schedule CRUD surface) with a distinguishing ``operation`` attribute,
matching every prior AI-IOS service's identical choice for the same
reason.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager

from opentelemetry.trace import Span, Tracer
from shared_core.telemetry.span import SpanType, start_span


@contextmanager
def trace_discovery_job(tracer: Tracer, *, job_id: str, **attributes: object) -> Iterator[Span]:
    """Trace one discovery job's full execution ("Discovery Jobs")."""
    with start_span(
        tracer, "discovery.job", span_type=SpanType.BACKGROUND_JOB, job_id=job_id, **attributes
    ) as span:
        yield span


@contextmanager
def trace_protocol_execution(
    tracer: Tracer, *, protocol: str, **attributes: object
) -> Iterator[Span]:
    """Trace one protocol probe ("Protocol Execution")."""
    with start_span(
        tracer,
        "discovery.protocol_execution",
        span_type=SpanType.BACKGROUND_JOB,
        protocol=protocol,
        **attributes,
    ) as span:
        yield span


@contextmanager
def trace_classification(tracer: Tracer, **attributes: object) -> Iterator[Span]:
    """Trace one asset classification decision ("Classification")."""
    with start_span(
        tracer, "discovery.classification", span_type=SpanType.BACKGROUND_JOB, **attributes
    ) as span:
        yield span


@contextmanager
def trace_synchronization(tracer: Tracer, **attributes: object) -> Iterator[Span]:
    """Trace one Inventory Service synchronization call ("Synchronization")."""
    with start_span(
        tracer, "discovery.synchronization", span_type=SpanType.BACKGROUND_JOB, **attributes
    ) as span:
        yield span


@contextmanager
def trace_topology_update(tracer: Tracer, **attributes: object) -> Iterator[Span]:
    """Trace one relationship/topology update ("Topology Updates")."""
    with start_span(
        tracer, "discovery.topology_update", span_type=SpanType.BACKGROUND_JOB, **attributes
    ) as span:
        yield span


@contextmanager
def trace_inventory_update(tracer: Tracer, **attributes: object) -> Iterator[Span]:
    """Trace one asset synchronized into the Inventory Service ("Inventory Updates")."""
    with start_span(
        tracer, "discovery.inventory_update", span_type=SpanType.BACKGROUND_JOB, **attributes
    ) as span:
        yield span


@contextmanager
def trace_performance_metrics(tracer: Tracer, **attributes: object) -> Iterator[Span]:
    """Trace one job's own aggregate performance metrics ("Performance Metrics")."""
    with start_span(
        tracer, "discovery.performance_metrics", span_type=SpanType.BACKGROUND_JOB, **attributes
    ) as span:
        yield span


__all__ = [
    "trace_classification",
    "trace_discovery_job",
    "trace_inventory_update",
    "trace_performance_metrics",
    "trace_protocol_execution",
    "trace_synchronization",
    "trace_topology_update",
]
