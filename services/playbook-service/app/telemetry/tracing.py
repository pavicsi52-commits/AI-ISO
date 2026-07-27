"""Playbook service telemetry.

Per docs/041 "TELEMETRY": Repository Access, Validation, Approval,
Publishing, Search, Downloads, Version Operations. No dedicated
:class:`~shared_core.telemetry.span.SpanType` member exists for any of
these, so every helper falls back to ``REST_API`` (or
``BACKGROUND_JOB`` for the validation path) with a distinguishing
``operation`` attribute, matching every prior AI-IOS service's
identical choice for the same reason.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager

from opentelemetry.trace import Span, Tracer
from shared_core.telemetry.span import SpanType, start_span


@contextmanager
def trace_repository_access(
    tracer: Tracer, *, operation: str, **attributes: object
) -> Iterator[Span]:
    """Trace one playbook-repository CRUD operation ("Repository Access")."""
    with start_span(
        tracer,
        "playbook.repository_access",
        span_type=SpanType.REST_API,
        operation=operation,
        **attributes,
    ) as span:
        yield span


@contextmanager
def trace_validation(tracer: Tracer, **attributes: object) -> Iterator[Span]:
    """Trace one structural content validation run ("Validation")."""
    with start_span(
        tracer, "playbook.validation", span_type=SpanType.BACKGROUND_JOB, **attributes
    ) as span:
        yield span


@contextmanager
def trace_approval(tracer: Tracer, *, operation: str, **attributes: object) -> Iterator[Span]:
    """Trace one approval-workflow request/decision step ("Approval")."""
    with start_span(
        tracer,
        "playbook.approval",
        span_type=SpanType.REST_API,
        operation=operation,
        **attributes,
    ) as span:
        yield span


@contextmanager
def trace_publishing(tracer: Tracer, **attributes: object) -> Iterator[Span]:
    """Trace one playbook publish/deprecate/archive status transition ("Publishing")."""
    with start_span(
        tracer, "playbook.publishing", span_type=SpanType.REST_API, **attributes
    ) as span:
        yield span


@contextmanager
def trace_search(tracer: Tracer, **attributes: object) -> Iterator[Span]:
    """Trace one playbook search/filter/sort query ("Search")."""
    with start_span(tracer, "playbook.search", span_type=SpanType.REST_API, **attributes) as span:
        yield span


@contextmanager
def trace_downloads(tracer: Tracer, **attributes: object) -> Iterator[Span]:
    """Trace one playbook content export/download ("Downloads")."""
    with start_span(
        tracer, "playbook.downloads", span_type=SpanType.REST_API, **attributes
    ) as span:
        yield span


@contextmanager
def trace_version_operation(
    tracer: Tracer, *, operation: str, **attributes: object
) -> Iterator[Span]:
    """Trace one version snapshot/diff/approval operation ("Version Operations")."""
    with start_span(
        tracer,
        "playbook.version_operation",
        span_type=SpanType.REST_API,
        operation=operation,
        **attributes,
    ) as span:
        yield span


__all__ = [
    "trace_approval",
    "trace_downloads",
    "trace_publishing",
    "trace_repository_access",
    "trace_search",
    "trace_validation",
    "trace_version_operation",
]
