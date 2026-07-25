"""Organization service telemetry.

Per docs/033 "TELEMETRY": Organization CRUD, Department Operations,
Quota Checks, License Validation, Analytics. "Integrate Prompt 024."
No dedicated :class:`~shared_core.telemetry.span.SpanType` member exists
for any of these, so every helper falls back to ``REST_API`` with a
distinguishing ``operation`` attribute, matching every prior AI-IOS
service's identical choice for the same reason.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager

from opentelemetry.trace import Span, Tracer
from shared_core.telemetry.span import SpanType, start_span


@contextmanager
def trace_organization_crud(
    tracer: Tracer, *, operation: str, **attributes: object
) -> Iterator[Span]:
    """Trace one organization CRUD operation ("Organization CRUD")."""
    with start_span(
        tracer, "organization.crud", span_type=SpanType.REST_API, operation=operation, **attributes
    ) as span:
        yield span


@contextmanager
def trace_department_operation(
    tracer: Tracer, *, operation: str, **attributes: object
) -> Iterator[Span]:
    """Trace one department operation ("Department Operations")."""
    with start_span(
        tracer,
        "organization.department",
        span_type=SpanType.REST_API,
        operation=operation,
        **attributes,
    ) as span:
        yield span


@contextmanager
def trace_quota_check(tracer: Tracer, **attributes: object) -> Iterator[Span]:
    """Trace one quota check ("Quota Checks")."""
    with start_span(
        tracer, "organization.quota_check", span_type=SpanType.REST_API, **attributes
    ) as span:
        yield span


@contextmanager
def trace_license_validation(tracer: Tracer, **attributes: object) -> Iterator[Span]:
    """Trace one license validation ("License Validation")."""
    with start_span(
        tracer, "organization.license_validation", span_type=SpanType.REST_API, **attributes
    ) as span:
        yield span


@contextmanager
def trace_analytics(tracer: Tracer, **attributes: object) -> Iterator[Span]:
    """Trace one analytics recompute ("Analytics")."""
    with start_span(
        tracer, "organization.analytics", span_type=SpanType.BACKGROUND_JOB, **attributes
    ) as span:
        yield span


__all__ = [
    "trace_analytics",
    "trace_department_operation",
    "trace_license_validation",
    "trace_organization_crud",
    "trace_quota_check",
]
