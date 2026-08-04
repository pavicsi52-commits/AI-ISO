"""Scheduler telemetry (docs/054 "TELEMETRY"): scheduling, dispatch, queue
time, execution, retries, recovery, worker performance.

Integrates ``shared_core.telemetry`` (Prompt 024).

No dedicated :class:`~shared_core.telemetry.span.SpanType` member exists
for scheduler work, so each span falls back to ``REST_API`` or
``BACKGROUND_JOB`` with a distinguishing name -- the same choice every
prior AI-IOS service made for the same reason.

**Every call below passes attributes via ``**{...}``, never a literal
``attributes={...}`` keyword.** ``start_span``'s own signature is
``start_span(tracer, name, *, span_type=None, **attributes)`` -- there is
no parameter actually named ``attributes``, only that catch-all. Passing
one anyway silently drops every attribute onto the floor instead of
raising, which is exactly the defect found and fixed in
``services/change-management-service``'s copy of this file (and
confirmed present in every other prior AI-IOS service's copy too) --
verified here by writing this file to be correct from the start, not
found after the fact.

**Spans carry identifiers and counts, never job content.** A job's own
``payload`` can carry sensitive data specific to whichever platform
service actually interprets it; it is stored deliberately and
access-controlled deliberately, and a tracing backend has different
retention and different access rules than that storage does.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager

from opentelemetry.trace import Span, Tracer
from shared_core.telemetry.span import SpanType, start_span


@contextmanager
def trace_scheduling(
    tracer: Tracer, *, job_id: str, trigger_type: str, **attributes: object
) -> Iterator[Span]:
    """Span computing one job's next-due time."""
    with start_span(
        tracer,
        "scheduler.schedule.compute",
        span_type=SpanType.BACKGROUND_JOB,
        **{"scheduler.job_id": job_id, "scheduler.trigger_type": trigger_type, **attributes},
    ) as span:
        yield span


@contextmanager
def trace_dispatch(
    tracer: Tracer, *, job_id: str, job_type: str, trigger_source: str, **attributes: object
) -> Iterator[Span]:
    """Span dispatching one job execution."""
    with start_span(
        tracer,
        "scheduler.dispatch",
        span_type=SpanType.REST_API,
        **{
            "scheduler.job_id": job_id,
            "scheduler.job_type": job_type,
            "scheduler.trigger_source": trigger_source,
            **attributes,
        },
    ) as span:
        yield span


@contextmanager
def trace_queue_time(
    tracer: Tracer, *, execution_id: str, queue_seconds: float, **attributes: object
) -> Iterator[Span]:
    """Span how long an execution waited between queued and running."""
    with start_span(
        tracer,
        "scheduler.queue.wait",
        span_type=SpanType.BACKGROUND_JOB,
        **{
            "scheduler.execution_id": execution_id,
            "scheduler.queue_seconds": queue_seconds,
            **attributes,
        },
    ) as span:
        yield span


@contextmanager
def trace_execution(
    tracer: Tracer, *, execution_id: str, status: str, **attributes: object
) -> Iterator[Span]:
    """Span one execution reaching a terminal status."""
    with start_span(
        tracer,
        "scheduler.execution",
        span_type=SpanType.BACKGROUND_JOB,
        **{"scheduler.execution_id": execution_id, "scheduler.status": status, **attributes},
    ) as span:
        yield span


@contextmanager
def trace_retry(
    tracer: Tracer, *, job_id: str, attempt_number: int, **attributes: object
) -> Iterator[Span]:
    """Span dispatching one retry attempt."""
    with start_span(
        tracer,
        "scheduler.retry",
        span_type=SpanType.BACKGROUND_JOB,
        **{"scheduler.job_id": job_id, "scheduler.attempt_number": attempt_number, **attributes},
    ) as span:
        yield span


@contextmanager
def trace_recovery(
    tracer: Tracer, *, failure_id: str, recovery_action: str, **attributes: object
) -> Iterator[Span]:
    """Span a manual failure recovery.

    Only the action taken, never the failure's own error detail -- an
    error message can echo back exactly the sensitive input that caused
    it, and a span is not where that belongs."""
    with start_span(
        tracer,
        "scheduler.recovery",
        span_type=SpanType.REST_API,
        **{
            "scheduler.failure_id": failure_id,
            "scheduler.recovery_action": recovery_action,
            **attributes,
        },
    ) as span:
        yield span


@contextmanager
def trace_worker_tick(
    tracer: Tracer, *, worker: str, processed: int, **attributes: object
) -> Iterator[Span]:
    """Span one background worker's sweep tick."""
    with start_span(
        tracer,
        "scheduler.worker.tick",
        span_type=SpanType.BACKGROUND_JOB,
        **{"scheduler.worker": worker, "scheduler.processed": processed, **attributes},
    ) as span:
        yield span


@contextmanager
def trace_publish(tracer: Tracer, *, event_name: str, **attributes: object) -> Iterator[Span]:
    """Span one domain-event publish."""
    with start_span(
        tracer,
        "scheduler.event.publish",
        span_type=SpanType.BACKGROUND_JOB,
        **{"scheduler.event": event_name, **attributes},
    ) as span:
        yield span


__all__ = [
    "trace_dispatch",
    "trace_execution",
    "trace_publish",
    "trace_queue_time",
    "trace_recovery",
    "trace_retry",
    "trace_scheduling",
    "trace_worker_tick",
]
