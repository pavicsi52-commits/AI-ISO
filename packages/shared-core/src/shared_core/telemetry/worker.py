"""Background job root trace.

Per docs/024_Enterprise_Telemetry_Framework.md.txt "MIDDLEWARE":
"Automatically create root traces for" Background Jobs. Also covers
"CONTEXT PROPAGATION": Background Workers -- if the job carries a
propagated context (e.g. injected by whatever enqueued it), this
continues that trace rather than starting an unrelated one.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager

from opentelemetry.trace import Span, Tracer

from shared_core.telemetry.propagation import extract_context, restore_context, use_context
from shared_core.telemetry.span import SpanType, start_span
from shared_core.telemetry.trace import start_root_trace


@contextmanager
def trace_background_job(
    tracer: Tracer, job_name: str, *, carrier: dict[str, str] | None = None, **attributes: str
) -> Iterator[Span]:
    """Start a background job's root trace ("Background Job").

    Continues a propagated context from *carrier* if given (e.g. the
    job's own stored metadata) -- the job's span then becomes a *child*
    of whatever enqueued it, not a disconnected new trace; with no
    carrier, starts a genuinely new, parentless trace.
    """
    name = f"job.{job_name}"
    if carrier is None:
        with start_root_trace(tracer, name, job_name=job_name, **attributes) as span:
            yield span
        return

    token = use_context(extract_context(carrier))
    try:
        with start_span(
            tracer, name, span_type=SpanType.BACKGROUND_JOB, job_name=job_name, **attributes
        ) as span:
            yield span
    finally:
        restore_context(token)


__all__ = ["trace_background_job"]
