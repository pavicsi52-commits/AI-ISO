"""Plugin Execution span helper.

Per docs/024_Enterprise_Telemetry_Framework.md.txt "SPAN TYPES": Plugin
Execution. Instruments the future Plugin SDK's executions without that
SDK depending on telemetry itself.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager

from opentelemetry.trace import Span, Tracer

from shared_core.telemetry.span import SpanType, start_span


@contextmanager
def trace_plugin_execution(tracer: Tracer, plugin_name: str, **attributes: str) -> Iterator[Span]:
    """Trace one plugin execution ("Plugin Execution")."""
    with start_span(
        tracer,
        f"plugin.execute {plugin_name}",
        span_type=SpanType.PLUGIN_EXECUTION,
        plugin_name=plugin_name,
        **attributes,
    ) as span:
        yield span


__all__ = ["trace_plugin_execution"]
