"""Knowledge graph telemetry.

Per docs/049 "TELEMETRY": Graph Queries, Synchronization, Cypher
Execution, Analytics, Traversal, Import, Export.

No dedicated :class:`~shared_core.telemetry.span.SpanType` member exists
for any of these, so each falls back to ``REST_API`` or
``BACKGROUND_JOB`` with a distinguishing span name -- the same choice
every prior AI-IOS service made for the same reason.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager

from opentelemetry.trace import Span, Tracer
from shared_core.telemetry.span import SpanType, start_span


@contextmanager
def trace_graph_query(tracer: Tracer, *, kind: str, **attributes: object) -> Iterator[Span]:
    """Trace one graph query."""
    with start_span(
        tracer, "graph.query", span_type=SpanType.REST_API, kind=kind, **attributes
    ) as span:
        yield span


@contextmanager
def trace_cypher(tracer: Tracer, *, statement: str, **attributes: object) -> Iterator[Span]:
    """Trace one Cypher execution.

    The statement is truncated into the span rather than attached whole:
    a span attribute is not a query log, and an unbounded one turns
    every trace into a copy of the query history.
    """
    with start_span(
        tracer,
        "graph.cypher",
        span_type=SpanType.REST_API,
        statement=statement[:200],
        **attributes,
    ) as span:
        yield span


@contextmanager
def trace_traversal(
    tracer: Tracer, *, root: str, depth: int, **attributes: object
) -> Iterator[Span]:
    """Trace one traversal."""
    with start_span(
        tracer,
        "graph.traversal",
        span_type=SpanType.REST_API,
        root=root,
        depth=depth,
        **attributes,
    ) as span:
        yield span


@contextmanager
def trace_synchronization(tracer: Tracer, *, source: str, **attributes: object) -> Iterator[Span]:
    """Trace one source synchronization."""
    with start_span(
        tracer,
        "graph.synchronization",
        span_type=SpanType.BACKGROUND_JOB,
        source=source,
        **attributes,
    ) as span:
        yield span


@contextmanager
def trace_analytics(tracer: Tracer, *, algorithm: str, **attributes: object) -> Iterator[Span]:
    """Trace one analytics computation."""
    with start_span(
        tracer,
        "graph.analytics",
        span_type=SpanType.BACKGROUND_JOB,
        algorithm=algorithm,
        **attributes,
    ) as span:
        yield span


@contextmanager
def trace_import(tracer: Tracer, *, graph_format: str, **attributes: object) -> Iterator[Span]:
    """Trace one graph import."""
    with start_span(
        tracer,
        "graph.import",
        span_type=SpanType.BACKGROUND_JOB,
        graph_format=graph_format,
        **attributes,
    ) as span:
        yield span


@contextmanager
def trace_export(tracer: Tracer, *, graph_format: str, **attributes: object) -> Iterator[Span]:
    """Trace one graph export."""
    with start_span(
        tracer,
        "graph.export",
        span_type=SpanType.BACKGROUND_JOB,
        graph_format=graph_format,
        **attributes,
    ) as span:
        yield span


__all__ = [
    "trace_analytics",
    "trace_cypher",
    "trace_export",
    "trace_graph_query",
    "trace_import",
    "trace_synchronization",
    "trace_traversal",
]
