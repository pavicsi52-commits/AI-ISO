"""Validation Step span helper.

Per docs/024_Enterprise_Telemetry_Framework.md.txt "SPAN TYPES":
Validation Step. Instruments :mod:`shared_core.validation` operations
without that package depending on telemetry itself.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager

from opentelemetry.trace import Span, Tracer

from shared_core.telemetry.span import SpanType, start_span


@contextmanager
def trace_validation_step(tracer: Tracer, validator_name: str, **attributes: str) -> Iterator[Span]:
    """Trace one validation step ("Validation Step"; "PERFORMANCE PROFILING": Validation)."""
    with start_span(
        tracer,
        f"validation.step {validator_name}",
        span_type=SpanType.VALIDATION_STEP,
        validator_name=validator_name,
        **attributes,
    ) as span:
        yield span


__all__ = ["trace_validation_step"]
