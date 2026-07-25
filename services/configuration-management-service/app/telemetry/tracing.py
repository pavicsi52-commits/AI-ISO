"""Configuration management service telemetry.

Per docs/039 "TELEMETRY": Configuration CRUD, Version Operations,
Drift Detection, Compliance Checks, Git Synchronization, Template
Processing, Rollback Operations. "Integrate Prompt 024." No dedicated
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
def trace_configuration_crud(
    tracer: Tracer, *, operation: str, **attributes: object
) -> Iterator[Span]:
    """Trace one configuration-profile CRUD operation ("Configuration CRUD")."""
    with start_span(
        tracer,
        "configuration_management.configuration_crud",
        span_type=SpanType.REST_API,
        operation=operation,
        **attributes,
    ) as span:
        yield span


@contextmanager
def trace_version_operation(
    tracer: Tracer, *, operation: str, **attributes: object
) -> Iterator[Span]:
    """Trace one version snapshot/rollback-target operation ("Version Operations")."""
    with start_span(
        tracer,
        "configuration_management.version_operation",
        span_type=SpanType.REST_API,
        operation=operation,
        **attributes,
    ) as span:
        yield span


@contextmanager
def trace_drift_detection(tracer: Tracer, **attributes: object) -> Iterator[Span]:
    """Trace one drift scan/report ("Drift Detection")."""
    with start_span(
        tracer,
        "configuration_management.drift_detection",
        span_type=SpanType.BACKGROUND_JOB,
        **attributes,
    ) as span:
        yield span


@contextmanager
def trace_compliance_check(tracer: Tracer, **attributes: object) -> Iterator[Span]:
    """Trace one compliance evaluation ("Compliance Checks")."""
    with start_span(
        tracer,
        "configuration_management.compliance_check",
        span_type=SpanType.REST_API,
        **attributes,
    ) as span:
        yield span


@contextmanager
def trace_git_synchronization(
    tracer: Tracer, *, provider: str, **attributes: object
) -> Iterator[Span]:
    """Trace one GitOps sync operation ("Git Synchronization")."""
    with start_span(
        tracer,
        "configuration_management.git_synchronization",
        span_type=SpanType.BACKGROUND_JOB,
        provider=provider,
        **attributes,
    ) as span:
        yield span


@contextmanager
def trace_template_processing(tracer: Tracer, **attributes: object) -> Iterator[Span]:
    """Trace one template render/instantiation ("Template Processing")."""
    with start_span(
        tracer,
        "configuration_management.template_processing",
        span_type=SpanType.REST_API,
        **attributes,
    ) as span:
        yield span


@contextmanager
def trace_rollback_operation(tracer: Tracer, **attributes: object) -> Iterator[Span]:
    """Trace one rollback initiate/approve/complete step ("Rollback Operations")."""
    with start_span(
        tracer,
        "configuration_management.rollback_operation",
        span_type=SpanType.REST_API,
        **attributes,
    ) as span:
        yield span


__all__ = [
    "trace_compliance_check",
    "trace_configuration_crud",
    "trace_drift_detection",
    "trace_git_synchronization",
    "trace_rollback_operation",
    "trace_template_processing",
    "trace_version_operation",
]
