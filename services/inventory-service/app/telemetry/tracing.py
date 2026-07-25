"""Inventory service telemetry.

Per docs/036 "TELEMETRY": Inventory CRUD, Topology Updates,
Relationship Queries, Imports, Exports, Synchronization, Search
Operations. "Integrate Prompt 024." No dedicated
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
def trace_inventory_crud(tracer: Tracer, *, operation: str, **attributes: object) -> Iterator[Span]:
    """Trace one asset CRUD operation ("Inventory CRUD")."""
    with start_span(
        tracer, "inventory.crud", span_type=SpanType.REST_API, operation=operation, **attributes
    ) as span:
        yield span


@contextmanager
def trace_topology_update(tracer: Tracer, **attributes: object) -> Iterator[Span]:
    """Trace one Neo4j topology mutation ("Topology Updates")."""
    with start_span(
        tracer, "inventory.topology_update", span_type=SpanType.REST_API, **attributes
    ) as span:
        yield span


@contextmanager
def trace_relationship_query(
    tracer: Tracer, *, query_kind: str, **attributes: object
) -> Iterator[Span]:
    """Trace one relationship/topology traversal query ("Relationship Queries")."""
    with start_span(
        tracer,
        "inventory.relationship_query",
        span_type=SpanType.REST_API,
        query_kind=query_kind,
        **attributes,
    ) as span:
        yield span


@contextmanager
def trace_import(tracer: Tracer, **attributes: object) -> Iterator[Span]:
    """Trace one bulk import job ("Imports")."""
    with start_span(
        tracer, "inventory.import", span_type=SpanType.BACKGROUND_JOB, **attributes
    ) as span:
        yield span


@contextmanager
def trace_export(tracer: Tracer, **attributes: object) -> Iterator[Span]:
    """Trace one bulk export job ("Exports")."""
    with start_span(
        tracer, "inventory.export", span_type=SpanType.BACKGROUND_JOB, **attributes
    ) as span:
        yield span


@contextmanager
def trace_synchronization(tracer: Tracer, **attributes: object) -> Iterator[Span]:
    """Trace one synchronization pass ("Synchronization")."""
    with start_span(
        tracer, "inventory.synchronization", span_type=SpanType.BACKGROUND_JOB, **attributes
    ) as span:
        yield span


@contextmanager
def trace_search(tracer: Tracer, **attributes: object) -> Iterator[Span]:
    """Trace one asset search ("Search Operations")."""
    with start_span(tracer, "inventory.search", span_type=SpanType.REST_API, **attributes) as span:
        yield span


__all__ = [
    "trace_export",
    "trace_import",
    "trace_inventory_crud",
    "trace_relationship_query",
    "trace_search",
    "trace_synchronization",
    "trace_topology_update",
]
