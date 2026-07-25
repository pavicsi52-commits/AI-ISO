"""Connector Execution span helper.

Per docs/024_Enterprise_Telemetry_Framework.md.txt "SPAN TYPES":
Connector Execution. Instruments the future Connector SDK's executions
without that SDK depending on telemetry itself.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager

from opentelemetry.trace import Span, Tracer

from shared_core.telemetry.span import SpanType, start_span


@contextmanager
def trace_connector_execution(
    tracer: Tracer, connector_name: str, **attributes: str
) -> Iterator[Span]:
    """Trace one connector execution ("Connector Execution")."""
    with start_span(
        tracer,
        f"connector.execute {connector_name}",
        span_type=SpanType.CONNECTOR_EXECUTION,
        connector_name=connector_name,
        **attributes,
    ) as span:
        yield span


__all__ = ["trace_connector_execution"]
