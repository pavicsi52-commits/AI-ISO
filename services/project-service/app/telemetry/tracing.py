"""Project service telemetry.

Per docs/034 "TELEMETRY": Project CRUD, Membership Changes, Settings
Updates, Project Search, Analytics Collection, Lifecycle Operations.
"Integrate Prompt 024." No dedicated
:class:`~shared_core.telemetry.span.SpanType` member exists for any of
these, so every helper falls back to ``REST_API`` with a distinguishing
``operation`` attribute, matching every prior AI-IOS service's
identical choice for the same reason.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager

from opentelemetry.trace import Span, Tracer
from shared_core.telemetry.span import SpanType, start_span


@contextmanager
def trace_project_crud(tracer: Tracer, *, operation: str, **attributes: object) -> Iterator[Span]:
    """Trace one project CRUD operation ("Project CRUD")."""
    with start_span(
        tracer, "project.crud", span_type=SpanType.REST_API, operation=operation, **attributes
    ) as span:
        yield span


@contextmanager
def trace_membership_change(
    tracer: Tracer, *, operation: str, **attributes: object
) -> Iterator[Span]:
    """Trace one membership change ("Membership Changes")."""
    with start_span(
        tracer, "project.membership", span_type=SpanType.REST_API, operation=operation, **attributes
    ) as span:
        yield span


@contextmanager
def trace_settings_update(tracer: Tracer, **attributes: object) -> Iterator[Span]:
    """Trace one settings update ("Settings Updates")."""
    with start_span(
        tracer, "project.settings_update", span_type=SpanType.REST_API, **attributes
    ) as span:
        yield span


@contextmanager
def trace_project_search(tracer: Tracer, **attributes: object) -> Iterator[Span]:
    """Trace one project search ("Project Search")."""
    with start_span(tracer, "project.search", span_type=SpanType.REST_API, **attributes) as span:
        yield span


@contextmanager
def trace_analytics(tracer: Tracer, **attributes: object) -> Iterator[Span]:
    """Trace one analytics recompute ("Analytics Collection")."""
    with start_span(
        tracer, "project.analytics", span_type=SpanType.BACKGROUND_JOB, **attributes
    ) as span:
        yield span


@contextmanager
def trace_lifecycle_operation(
    tracer: Tracer, *, operation: str, **attributes: object
) -> Iterator[Span]:
    """Trace one lifecycle operation ("Lifecycle Operations": clone/archive/restore)."""
    with start_span(
        tracer, "project.lifecycle", span_type=SpanType.REST_API, operation=operation, **attributes
    ) as span:
        yield span


__all__ = [
    "trace_analytics",
    "trace_lifecycle_operation",
    "trace_membership_change",
    "trace_project_crud",
    "trace_project_search",
    "trace_settings_update",
]
