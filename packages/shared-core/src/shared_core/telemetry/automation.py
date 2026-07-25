"""Automation Step span helper.

Per docs/024_Enterprise_Telemetry_Framework.md.txt "SPAN TYPES":
Automation Step. Instruments the future Automation Engine's step
executions without that engine depending on telemetry itself.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager

from opentelemetry.trace import Span, Tracer

from shared_core.telemetry.span import SpanType, start_span


@contextmanager
def trace_automation_step(
    tracer: Tracer, automation_name: str, step_name: str, **attributes: str
) -> Iterator[Span]:
    """Trace one automation step ("Automation Step"; "PERFORMANCE PROFILING": Automation)."""
    with start_span(
        tracer,
        f"automation.step {automation_name}.{step_name}",
        span_type=SpanType.AUTOMATION_STEP,
        automation_name=automation_name,
        step_name=step_name,
        **attributes,
    ) as span:
        yield span


__all__ = ["trace_automation_step"]
