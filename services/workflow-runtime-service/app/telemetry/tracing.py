"""Workflow runtime service telemetry.

Per docs/042 "TELEMETRY": Workflow Runtime, Node Execution, Queue
Processing, Checkpoint, Replay, Rollback, Approval, State Transitions.
No dedicated :class:`~shared_core.telemetry.span.SpanType` member exists
for any of these, so every helper falls back to ``REST_API`` (or
``BACKGROUND_JOB`` for the runtime/queue paths) with a distinguishing
``operation`` attribute, matching every prior AI-IOS service's
identical choice for the same reason.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager

from opentelemetry.trace import Span, Tracer
from shared_core.telemetry.span import SpanType, start_span


@contextmanager
def trace_workflow_runtime(
    tracer: Tracer, *, operation: str, **attributes: object
) -> Iterator[Span]:
    """Trace one workflow instance's own end-to-end run ("Workflow Runtime")."""
    with start_span(
        tracer,
        "workflow_runtime.instance",
        span_type=SpanType.BACKGROUND_JOB,
        operation=operation,
        **attributes,
    ) as span:
        yield span


@contextmanager
def trace_node_execution(tracer: Tracer, *, node_id: str, **attributes: object) -> Iterator[Span]:
    """Trace one DAG node's own execution ("Node Execution")."""
    with start_span(
        tracer,
        "workflow_runtime.node_execution",
        span_type=SpanType.REST_API,
        node_id=node_id,
        **attributes,
    ) as span:
        yield span


@contextmanager
def trace_queue_processing(tracer: Tracer, **attributes: object) -> Iterator[Span]:
    """Trace one queue-consumed execution dispatch ("Queue Processing")."""
    with start_span(
        tracer, "workflow_runtime.queue_processing", span_type=SpanType.BACKGROUND_JOB, **attributes
    ) as span:
        yield span


@contextmanager
def trace_checkpoint(tracer: Tracer, **attributes: object) -> Iterator[Span]:
    """Trace one checkpoint persistence operation ("Checkpoint")."""
    with start_span(
        tracer, "workflow_runtime.checkpoint", span_type=SpanType.REST_API, **attributes
    ) as span:
        yield span


@contextmanager
def trace_replay(tracer: Tracer, **attributes: object) -> Iterator[Span]:
    """Trace one replay run ("Replay")."""
    with start_span(
        tracer, "workflow_runtime.replay", span_type=SpanType.REST_API, **attributes
    ) as span:
        yield span


@contextmanager
def trace_rollback(tracer: Tracer, **attributes: object) -> Iterator[Span]:
    """Trace one rollback operation ("Rollback")."""
    with start_span(
        tracer, "workflow_runtime.rollback", span_type=SpanType.REST_API, **attributes
    ) as span:
        yield span


@contextmanager
def trace_approval(tracer: Tracer, *, operation: str, **attributes: object) -> Iterator[Span]:
    """Trace one approval request/decision step ("Approval")."""
    with start_span(
        tracer,
        "workflow_runtime.approval",
        span_type=SpanType.REST_API,
        operation=operation,
        **attributes,
    ) as span:
        yield span


@contextmanager
def trace_state_transition(
    tracer: Tracer, *, to_status: str, **attributes: object
) -> Iterator[Span]:
    """Trace one state transition ("State Transitions")."""
    with start_span(
        tracer,
        "workflow_runtime.state_transition",
        span_type=SpanType.REST_API,
        to_status=to_status,
        **attributes,
    ) as span:
        yield span


__all__ = [
    "trace_approval",
    "trace_checkpoint",
    "trace_node_execution",
    "trace_queue_processing",
    "trace_replay",
    "trace_rollback",
    "trace_state_transition",
    "trace_workflow_runtime",
]
