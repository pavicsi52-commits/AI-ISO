"""Reporting telemetry.

Per docs/047 "TELEMETRY": Rendering, Export, Distribution, Scheduling,
Archive, Template Rendering. No dedicated
:class:`~shared_core.telemetry.span.SpanType` member exists for any of
these, so each falls back to ``REST_API`` or ``BACKGROUND_JOB`` with a
distinguishing span name -- the same choice every prior AI-IOS service
made for the same reason.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager

from opentelemetry.trace import Span, Tracer
from shared_core.telemetry.span import SpanType, start_span


@contextmanager
def trace_rendering(tracer: Tracer, *, report: str, **attributes: object) -> Iterator[Span]:
    """Trace resolving one report definition into data."""
    with start_span(
        tracer, "report.rendering", span_type=SpanType.REST_API, report=report, **attributes
    ) as span:
        yield span


@contextmanager
def trace_template_rendering(
    tracer: Tracer, *, template: str, **attributes: object
) -> Iterator[Span]:
    """Trace rendering one template's own sections."""
    with start_span(
        tracer,
        "report.template_rendering",
        span_type=SpanType.REST_API,
        template=template,
        **attributes,
    ) as span:
        yield span


@contextmanager
def trace_export(tracer: Tracer, *, export_format: str, **attributes: object) -> Iterator[Span]:
    """Trace serialising a rendered report to one format."""
    with start_span(
        tracer,
        "report.export",
        span_type=SpanType.BACKGROUND_JOB,
        export_format=export_format,
        **attributes,
    ) as span:
        yield span


@contextmanager
def trace_distribution(tracer: Tracer, *, channel: str, **attributes: object) -> Iterator[Span]:
    """Trace one delivery attempt."""
    with start_span(
        tracer,
        "report.distribution",
        span_type=SpanType.BACKGROUND_JOB,
        channel=channel,
        **attributes,
    ) as span:
        yield span


@contextmanager
def trace_scheduling(tracer: Tracer, *, schedule: str, **attributes: object) -> Iterator[Span]:
    """Trace one scheduled run being dispatched."""
    with start_span(
        tracer,
        "report.scheduling",
        span_type=SpanType.BACKGROUND_JOB,
        schedule=schedule,
        **attributes,
    ) as span:
        yield span


@contextmanager
def trace_archive(tracer: Tracer, *, operation: str, **attributes: object) -> Iterator[Span]:
    """Trace an archive operation (store, restore, purge)."""
    with start_span(
        tracer,
        "report.archive",
        span_type=SpanType.BACKGROUND_JOB,
        operation=operation,
        **attributes,
    ) as span:
        yield span


__all__ = [
    "trace_archive",
    "trace_distribution",
    "trace_export",
    "trace_rendering",
    "trace_scheduling",
    "trace_template_rendering",
]
