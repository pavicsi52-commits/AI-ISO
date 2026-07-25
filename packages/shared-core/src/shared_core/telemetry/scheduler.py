"""Scheduler job root trace.

Per docs/024_Enterprise_Telemetry_Framework.md.txt "MIDDLEWARE":
"Automatically create root traces for" Scheduler Tasks. Also covers
"CONTEXT PROPAGATION": Scheduler Jobs -- if the job carries a
propagated context (e.g. stored alongside a
:class:`~shared_core.queue.scheduler.ScheduledTask`), this continues
that trace rather than starting an unrelated one.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager

from opentelemetry.trace import Span, Tracer

from shared_core.telemetry.propagation import extract_context, restore_context, use_context
from shared_core.telemetry.span import SpanType, start_span
from shared_core.telemetry.trace import start_root_trace


@contextmanager
def trace_scheduler_job(
    tracer: Tracer, task_name: str, *, carrier: dict[str, str] | None = None, **attributes: str
) -> Iterator[Span]:
    """Start a scheduled task run's root trace ("Scheduler Job").

    Continues a propagated context from *carrier* if given; otherwise
    starts a genuinely new, parentless trace -- the common case, since
    most scheduled tasks (cron-style) have no "caller" to continue from.
    """
    name = f"scheduler.{task_name}"
    if carrier is None:
        with start_root_trace(tracer, name, task_name=task_name, **attributes) as span:
            yield span
        return

    token = use_context(extract_context(carrier))
    try:
        with start_span(
            tracer, name, span_type=SpanType.SCHEDULER_JOB, task_name=task_name, **attributes
        ) as span:
            yield span
    finally:
        restore_context(token)


__all__ = ["trace_scheduler_job"]
