"""Dashboard telemetry.

Per docs/048 "TELEMETRY": Dashboard Loading, Widget Rendering,
Topology Rendering, Real-time Streaming, API Calls, Filter Execution.
No dedicated :class:`~shared_core.telemetry.span.SpanType` member
exists for any of these, so each falls back to ``REST_API`` or
``BACKGROUND_JOB`` with a distinguishing span name -- the same choice
every prior AI-IOS service made for the same reason.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager

from opentelemetry.trace import Span, Tracer
from shared_core.telemetry.span import SpanType, start_span


@contextmanager
def trace_dashboard_load(tracer: Tracer, *, dashboard: str, **attributes: object) -> Iterator[Span]:
    """Trace one full dashboard load."""
    with start_span(
        tracer, "dashboard.load", span_type=SpanType.REST_API, dashboard=dashboard, **attributes
    ) as span:
        yield span


@contextmanager
def trace_widget_render(tracer: Tracer, *, widget: str, **attributes: object) -> Iterator[Span]:
    """Trace resolving one widget."""
    with start_span(
        tracer,
        "dashboard.widget_render",
        span_type=SpanType.BACKGROUND_JOB,
        widget=widget,
        **attributes,
    ) as span:
        yield span


@contextmanager
def trace_topology_render(tracer: Tracer, *, root: str, **attributes: object) -> Iterator[Span]:
    """Trace one topology traversal."""
    with start_span(
        tracer,
        "dashboard.topology_render",
        span_type=SpanType.BACKGROUND_JOB,
        root=root,
        **attributes,
    ) as span:
        yield span


@contextmanager
def trace_streaming(tracer: Tracer, *, dashboard: str, **attributes: object) -> Iterator[Span]:
    """Trace one real-time subscription."""
    with start_span(
        tracer,
        "dashboard.streaming",
        span_type=SpanType.BACKGROUND_JOB,
        dashboard=dashboard,
        **attributes,
    ) as span:
        yield span


@contextmanager
def trace_filter_execution(tracer: Tracer, *, clauses: int, **attributes: object) -> Iterator[Span]:
    """Trace applying a filter set."""
    with start_span(
        tracer,
        "dashboard.filter_execution",
        span_type=SpanType.BACKGROUND_JOB,
        clauses=clauses,
        **attributes,
    ) as span:
        yield span


__all__ = [
    "trace_dashboard_load",
    "trace_filter_execution",
    "trace_streaming",
    "trace_topology_render",
    "trace_widget_render",
]
