"""Automation service telemetry.

Per docs/040 "TELEMETRY": Execution Engine, Connector Calls, Workflow
Execution, Inventory Resolution, Secrets Access, Execution Timing,
Queue Operations. No dedicated
:class:`~shared_core.telemetry.span.SpanType` member exists for any of
these, so every helper falls back to ``REST_API`` (or
``BACKGROUND_JOB`` for the queue-worker/dispatch paths) with a
distinguishing ``operation`` attribute, matching every prior AI-IOS
service's identical choice for the same reason.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager

from opentelemetry.trace import Span, Tracer
from shared_core.telemetry.span import SpanType, start_span


@contextmanager
def trace_execution_engine(
    tracer: Tracer, *, operation: str, **attributes: object
) -> Iterator[Span]:
    """Trace one execution-engine orchestration step ("Execution Engine")."""
    with start_span(
        tracer,
        "automation.execution_engine",
        span_type=SpanType.BACKGROUND_JOB,
        operation=operation,
        **attributes,
    ) as span:
        yield span


@contextmanager
def trace_connector_call(
    tracer: Tracer, *, connector_type: str, **attributes: object
) -> Iterator[Span]:
    """Trace one runner/connector dispatch call ("Connector Calls")."""
    with start_span(
        tracer,
        "automation.connector_call",
        span_type=SpanType.BACKGROUND_JOB,
        connector_type=connector_type,
        **attributes,
    ) as span:
        yield span


@contextmanager
def trace_workflow_execution(tracer: Tracer, **attributes: object) -> Iterator[Span]:
    """Trace one Workflow SDK node handler invocation ("Workflow Execution")."""
    with start_span(
        tracer, "automation.workflow_execution", span_type=SpanType.BACKGROUND_JOB, **attributes
    ) as span:
        yield span


@contextmanager
def trace_inventory_resolution(tracer: Tracer, **attributes: object) -> Iterator[Span]:
    """Trace one inventory-service target lookup ("Inventory Resolution")."""
    with start_span(
        tracer, "automation.inventory_resolution", span_type=SpanType.REST_API, **attributes
    ) as span:
        yield span


@contextmanager
def trace_secrets_access(tracer: Tracer, **attributes: object) -> Iterator[Span]:
    """Trace one secrets-service credential resolution ("Secrets Access")."""
    with start_span(
        tracer, "automation.secrets_access", span_type=SpanType.REST_API, **attributes
    ) as span:
        yield span


@contextmanager
def trace_execution_timing(tracer: Tracer, *, job_id: str, **attributes: object) -> Iterator[Span]:
    """Trace one execution's end-to-end wall-clock duration ("Execution Timing")."""
    with start_span(
        tracer,
        "automation.execution_timing",
        span_type=SpanType.BACKGROUND_JOB,
        job_id=job_id,
        **attributes,
    ) as span:
        yield span


@contextmanager
def trace_queue_operation(
    tracer: Tracer, *, operation: str, **attributes: object
) -> Iterator[Span]:
    """Trace one queue enqueue/dequeue operation ("Queue Operations")."""
    with start_span(
        tracer,
        "automation.queue_operation",
        span_type=SpanType.BACKGROUND_JOB,
        operation=operation,
        **attributes,
    ) as span:
        yield span


__all__ = [
    "trace_connector_call",
    "trace_execution_engine",
    "trace_execution_timing",
    "trace_inventory_resolution",
    "trace_queue_operation",
    "trace_secrets_access",
    "trace_workflow_execution",
]
