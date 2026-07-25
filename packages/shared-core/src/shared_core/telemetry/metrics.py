"""Metrics correlation.

Per docs/024_Enterprise_Telemetry_Framework.md.txt "METRICS
CORRELATION": associate metrics with traces. Track Latency, Request
Count, Error Count, CPU, Memory, Queue Depth, Database Time, Cache
Time, Storage Time, Workflow Duration, Automation Duration, Validation
Duration, Inference Duration.

Most of this list already has a real Prometheus instrument elsewhere,
deliberately not redefined here: Request Count/Latency
(``shared_core.metrics.standard``, Prompt 012), CPU/Memory
(``shared_core.monitoring.application``, Prompt 023), Queue Depth
(``shared_core.queue.metrics``, Prompt 021), Workflow/Automation/
Validation/Inference Duration (``shared_core.monitoring.metrics``,
Prompt 023). What's genuinely new is: the three durations with no
existing histogram yet (Database Time, Cache Time, Storage Time), and
the correlation mechanism itself -- :func:`observe_with_trace_exemplar`
attaches the *current trace's* ID to any histogram observation (new or
reused) as a Prometheus exemplar, so a metrics backend that supports
exemplars (e.g. Grafana + Prometheus with the feature enabled) can jump
straight from a latency spike to the trace that caused it.
"""

from __future__ import annotations

from prometheus_client import Histogram

from shared_core.metrics.registry import create_histogram
from shared_core.telemetry.context import current_span_ids

database_time_seconds = create_histogram(
    "database_time_seconds", "Time spent on a database operation, in seconds.", labels=["operation"]
)
cache_time_seconds = create_histogram(
    "cache_time_seconds", "Time spent on a cache operation, in seconds.", labels=["operation"]
)
storage_time_seconds = create_histogram(
    "storage_time_seconds", "Time spent on a storage operation, in seconds.", labels=["operation"]
)


def observe_with_trace_exemplar(histogram: Histogram, value: float, **labels: str) -> None:
    """Observe *value* into *histogram*, attaching the current trace ID as an exemplar.

    A no-op exemplar (an ordinary observation) if no trace is currently
    active -- correlation is best-effort, never a reason to fail or skip
    recording the metric itself.
    """
    target = histogram.labels(**labels) if labels else histogram
    trace_id, _span_id, _parent_span_id = current_span_ids()
    if trace_id is None:
        target.observe(value)
        return
    target.observe(value, exemplar={"trace_id": trace_id})


__all__ = [
    "cache_time_seconds",
    "database_time_seconds",
    "observe_with_trace_exemplar",
    "storage_time_seconds",
]
