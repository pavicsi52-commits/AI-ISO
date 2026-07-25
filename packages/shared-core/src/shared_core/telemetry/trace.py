"""Tracer access and root trace creation.

Per docs/024_Enterprise_Telemetry_Framework.md.txt "TELEMETRY PRINCIPLES":
"Every request shall be traceable" and "Every span shall have a parent"
-- a root trace is the one exception, deliberately started with no
parent, so every subsequent span in the same logical operation (an HTTP
request, a background job, a scheduler run) has *something* to attach to.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager

from opentelemetry import context as otel_context
from opentelemetry import trace
from opentelemetry.trace import Span, Tracer


def get_tracer(name: str) -> Tracer:
    """Return a tracer for instrumenting a module, from the globally configured provider."""
    return trace.get_tracer(name)


@contextmanager
def start_root_trace(tracer: Tracer, name: str, **attributes: str) -> Iterator[Span]:
    """Start a new trace with no parent ("DISTRIBUTED TRACING": entry points).

    Detaches from any currently active span first, so a root trace never
    accidentally nests under a leftover span from unrelated prior work
    on the same task/thread (e.g. a worker's next job after a previous
    one's trace wasn't fully torn down).
    """
    token = otel_context.attach(otel_context.Context())
    try:
        with tracer.start_as_current_span(name, attributes=attributes) as span:
            yield span
    finally:
        otel_context.detach(token)


def is_traced() -> bool:
    """Whether a valid span is currently active ("Every operation shall belong to a trace")."""
    return trace.get_current_span().get_span_context().is_valid


__all__ = ["get_tracer", "is_traced", "start_root_trace"]
