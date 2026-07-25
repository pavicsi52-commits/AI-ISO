"""Plugin telemetry.

Per docs/029_Enterprise_Plugin_Framework.md.txt "TELEMETRY": Trace
Plugin Load, Execution, Hooks, Errors, Lifecycle Events. Reuses
:func:`shared_core.telemetry.plugin.trace_plugin_execution` directly --
Prompt 024 had already built this exact "Plugin Execution" span type in
anticipation of this prompt -- distinguishing load/hook/lifecycle
tracing via an ``operation`` span attribute rather than adding new
span types for what is really the same span shape.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager

from opentelemetry.trace import Span, Tracer

from shared_core.telemetry.plugin import trace_plugin_execution


@contextmanager
def trace_plugin_load(tracer: Tracer, plugin_id: str) -> Iterator[Span]:
    """Trace one plugin's dynamic load ("Plugin Load")."""
    with trace_plugin_execution(tracer, plugin_id, operation="load") as span:
        yield span


@contextmanager
def trace_plugin_hook(tracer: Tracer, plugin_id: str, hook_name: str) -> Iterator[Span]:
    """Trace one hook callback's execution ("Hooks")."""
    with trace_plugin_execution(tracer, plugin_id, operation="hook", hook_name=hook_name) as span:
        yield span


@contextmanager
def trace_plugin_lifecycle(tracer: Tracer, plugin_id: str, transition: str) -> Iterator[Span]:
    """Trace one lifecycle state transition ("Lifecycle Events")."""
    with trace_plugin_execution(
        tracer, plugin_id, operation="lifecycle", transition=transition
    ) as span:
        yield span


__all__ = [
    "trace_plugin_execution",
    "trace_plugin_hook",
    "trace_plugin_lifecycle",
    "trace_plugin_load",
]
