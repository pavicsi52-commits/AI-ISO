"""Cache Access span helper.

Per docs/024_Enterprise_Telemetry_Framework.md.txt "SPAN TYPES": Cache
Access. Instruments :mod:`shared_core.cache` operations without that
package depending on telemetry itself.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager

from opentelemetry.trace import Span, Tracer

from shared_core.telemetry.span import SpanType, start_span


@contextmanager
def trace_cache_access(
    tracer: Tracer, operation: str, *, key: str | None = None, **attributes: str
) -> Iterator[Span]:
    """Trace one cache operation ("Cache Access"; "PERFORMANCE PROFILING": Redis Operations)."""
    if key is not None:
        attributes["cache.key"] = key
    with start_span(
        tracer, f"cache.{operation}", span_type=SpanType.CACHE_ACCESS, **attributes
    ) as span:
        yield span


__all__ = ["trace_cache_access"]
