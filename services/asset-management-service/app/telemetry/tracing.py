"""Asset management service telemetry.

Per docs/038 "TELEMETRY": Asset Operations, Maintenance, Compliance,
Risk Analysis, Cost Analysis, Dependency Queries, Health Aggregation.
"Integrate Prompt 024." No dedicated
:class:`~shared_core.telemetry.span.SpanType` member exists for any of
these, so every helper falls back to ``REST_API`` (or
``BACKGROUND_JOB`` for the queue-worker paths) with a distinguishing
``operation`` attribute, matching every prior AI-IOS service's
identical choice for the same reason.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager

from opentelemetry.trace import Span, Tracer
from shared_core.telemetry.span import SpanType, start_span


@contextmanager
def trace_asset_operation(
    tracer: Tracer, *, operation: str, **attributes: object
) -> Iterator[Span]:
    """Trace one managed-asset CRUD operation ("Asset Operations")."""
    with start_span(
        tracer,
        "asset_management.asset_operation",
        span_type=SpanType.REST_API,
        operation=operation,
        **attributes,
    ) as span:
        yield span


@contextmanager
def trace_maintenance(tracer: Tracer, **attributes: object) -> Iterator[Span]:
    """Trace one maintenance operation ("Maintenance")."""
    with start_span(
        tracer, "asset_management.maintenance", span_type=SpanType.REST_API, **attributes
    ) as span:
        yield span


@contextmanager
def trace_compliance(tracer: Tracer, **attributes: object) -> Iterator[Span]:
    """Trace one compliance evaluation ("Compliance")."""
    with start_span(
        tracer, "asset_management.compliance", span_type=SpanType.REST_API, **attributes
    ) as span:
        yield span


@contextmanager
def trace_risk_analysis(tracer: Tracer, **attributes: object) -> Iterator[Span]:
    """Trace one risk evaluation ("Risk Analysis")."""
    with start_span(
        tracer, "asset_management.risk_analysis", span_type=SpanType.REST_API, **attributes
    ) as span:
        yield span


@contextmanager
def trace_cost_analysis(tracer: Tracer, **attributes: object) -> Iterator[Span]:
    """Trace one cost computation ("Cost Analysis")."""
    with start_span(
        tracer, "asset_management.cost_analysis", span_type=SpanType.REST_API, **attributes
    ) as span:
        yield span


@contextmanager
def trace_dependency_query(
    tracer: Tracer, *, query_kind: str, **attributes: object
) -> Iterator[Span]:
    """Trace one Neo4j dependency-graph query ("Dependency Queries")."""
    with start_span(
        tracer,
        "asset_management.dependency_query",
        span_type=SpanType.REST_API,
        query_kind=query_kind,
        **attributes,
    ) as span:
        yield span


@contextmanager
def trace_health_aggregation(tracer: Tracer, **attributes: object) -> Iterator[Span]:
    """Trace one health rollup computation ("Health Aggregation")."""
    with start_span(
        tracer,
        "asset_management.health_aggregation",
        span_type=SpanType.BACKGROUND_JOB,
        **attributes,
    ) as span:
        yield span


__all__ = [
    "trace_asset_operation",
    "trace_compliance",
    "trace_cost_analysis",
    "trace_dependency_query",
    "trace_health_aggregation",
    "trace_maintenance",
    "trace_risk_analysis",
]
