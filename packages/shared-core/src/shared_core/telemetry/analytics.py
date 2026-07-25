"""Trace analytics.

Per docs/024_Enterprise_Telemetry_Framework.md.txt "ANALYTICS": Trace
Search, Slowest Requests, Slowest Queries, Service Dependency Graph,
Error Hotspots, Top Exceptions, P50/P90/P95/P99, Average Latency,
Throughput.

Purely in-process (this framework must not run a Jaeger/Tempo server --
docs/024 "DO NOT IMPLEMENT"): :class:`TraceRecorder` is a bounded,
process-lifetime buffer of recently completed root traces, fed by a real
:class:`~opentelemetry.sdk.trace.SpanProcessor` hook (:class:`AnalyticsSpanProcessor`)
rather than requiring callers to manually record anything. A service
wanting trace history across a fleet, surviving a restart, is expected
to query its OTLP collector's own backend (Tempo/Jaeger/...), not this
module -- the same "purely in-process, be honest about the limit" stance
as :mod:`shared_core.monitoring.availability`.
"""

from __future__ import annotations

import time
from collections import Counter, deque
from dataclasses import dataclass
from typing import TYPE_CHECKING

from opentelemetry.sdk.trace import SpanProcessor
from opentelemetry.trace import StatusCode

from shared_core.telemetry.constants import DEFAULT_RECENT_TRACE_BUFFER_SIZE

if TYPE_CHECKING:
    from opentelemetry.sdk.trace import ReadableSpan


@dataclass(frozen=True, slots=True)
class TraceSummary:
    """A lightweight record of one completed root trace."""

    trace_id: str
    name: str
    service_name: str
    duration_ms: float
    is_error: bool
    completed_at: float


@dataclass(frozen=True, slots=True)
class SpanEdge:
    """One parent-to-child service call, for the service dependency graph."""

    from_service: str
    to_service: str


class TraceRecorder:
    """A bounded, in-memory buffer of recently completed traces and cross-service call edges."""

    def __init__(self, *, max_size: int = DEFAULT_RECENT_TRACE_BUFFER_SIZE):
        self._traces: deque[TraceSummary] = deque(maxlen=max_size)
        self._edges: Counter[SpanEdge] = Counter()
        # Best-effort span_id -> service_name lookup for the dependency graph,
        # populated as spans end; bounded the same way, so a parent whose
        # children ended long ago (and were evicted) won't resolve an edge.
        self._max_span_service_entries = max_size * 8
        self._span_services: dict[str, str] = {}
        self._span_service_order: deque[str] = deque(maxlen=self._max_span_service_entries)

    def record_trace(self, summary: TraceSummary) -> None:
        """Record one completed root trace."""
        self._traces.append(summary)

    def record_span_service(self, span_id: str, service_name: str) -> None:
        """Remember which service emitted *span_id*, for dependency-graph resolution."""
        self._span_services[span_id] = service_name
        self._span_service_order.append(span_id)
        while len(self._span_service_order) > self._max_span_service_entries:
            evicted = self._span_service_order.popleft()
            self._span_services.pop(evicted, None)

    def record_edge(self, parent_span_id: str | None, service_name: str) -> None:
        """Record a call from whatever service owns *parent_span_id* to *service_name*."""
        if parent_span_id is None:
            return
        parent_service = self._span_services.get(parent_span_id)
        if parent_service is not None and parent_service != service_name:
            self._edges[SpanEdge(parent_service, service_name)] += 1

    def traces(self) -> list[TraceSummary]:
        """Every currently retained trace, oldest first."""
        return list(self._traces)

    def slowest_traces(self, n: int = 10) -> list[TraceSummary]:
        """The *n* slowest currently retained traces ("Slowest Requests"/"Slowest Queries")."""
        return sorted(self._traces, key=lambda t: t.duration_ms, reverse=True)[:n]

    def error_hotspots(self, n: int = 10) -> list[tuple[str, int]]:
        """The *n* trace names with the most errored traces ("Error Hotspots")."""
        counts = Counter(t.name for t in self._traces if t.is_error)
        return counts.most_common(n)

    def percentile_latency_ms(self, percentile: float) -> float:
        """The *percentile* (0-100) latency across retained traces. ``0.0`` if none retained."""
        if not self._traces:
            return 0.0
        durations = sorted(t.duration_ms for t in self._traces)
        rank = max(0, min(len(durations) - 1, round(percentile / 100 * (len(durations) - 1))))
        return durations[rank]

    def average_latency_ms(self) -> float:
        """The mean latency across retained traces ("Average Latency"). ``0.0`` if none."""
        if not self._traces:
            return 0.0
        return sum(t.duration_ms for t in self._traces) / len(self._traces)

    def throughput_per_second(self, *, window_seconds: float = 60.0) -> float:
        """Completed traces per second over the last *window_seconds* ("Throughput")."""
        cutoff = time.time() - window_seconds
        recent = [t for t in self._traces if t.completed_at >= cutoff]
        if not recent:
            return 0.0
        return len(recent) / window_seconds

    def search(
        self, *, name_contains: str | None = None, errors_only: bool = False
    ) -> list[TraceSummary]:
        """Search retained traces by name substring and/or error status ("Trace Search")."""
        results = list(self._traces)
        if name_contains is not None:
            results = [t for t in results if name_contains in t.name]
        if errors_only:
            results = [t for t in results if t.is_error]
        return results

    def service_dependency_graph(self) -> list[SpanEdge]:
        """Best-effort service-to-service call edges observed so far ("Dependency Graph")."""
        return [edge for edge, _count in self._edges.most_common()]


class AnalyticsSpanProcessor(SpanProcessor):
    """Feeds a :class:`TraceRecorder` from real span completions.

    Registered alongside the export span processor
    (:func:`shared_core.telemetry.provider.configure_tracing` accepts
    only one processor directly, so wrap both in a
    :class:`~opentelemetry.sdk.trace.export.SimpleSpanProcessor`-style
    composite, or add this one separately via
    ``TracerProvider.add_span_processor``) -- observes every span for
    the dependency graph, but only records full :class:`TraceSummary`
    entries for root spans (``span.parent is None``), matching
    docs/024's "Trace Search"/"Slowest Requests" scope of whole traces,
    not individual spans.
    """

    def __init__(self, recorder: TraceRecorder):
        self._recorder = recorder

    def on_start(self, span: ReadableSpan, parent_context: object = None) -> None:
        # Recorded on start, not end: nested spans END in the reverse order
        # they started (innermost first), so a child's on_end -- needing its
        # parent's service already resolved -- would otherwise almost always
        # run before the parent ever recorded itself.
        context = span.get_span_context()
        if context is None or not context.is_valid:
            return
        service_name = str((span.resource.attributes or {}).get("service.name", "unknown"))
        span_id = format(context.span_id, "016x")
        self._recorder.record_span_service(span_id, service_name)

    def on_end(self, span: ReadableSpan) -> None:
        context = span.get_span_context()
        if context is None or not context.is_valid:
            return
        service_name = str((span.resource.attributes or {}).get("service.name", "unknown"))

        parent_span_id = format(span.parent.span_id, "016x") if span.parent is not None else None
        self._recorder.record_edge(parent_span_id, service_name)

        if span.parent is None:
            duration_ms = (
                (span.end_time - span.start_time) / 1_000_000
                if span.end_time is not None and span.start_time is not None
                else 0.0
            )
            is_error = span.status is not None and span.status.status_code == StatusCode.ERROR
            self._recorder.record_trace(
                TraceSummary(
                    trace_id=format(context.trace_id, "032x"),
                    name=span.name,
                    service_name=service_name,
                    duration_ms=duration_ms,
                    is_error=is_error,
                    completed_at=time.time(),
                )
            )

    def shutdown(self) -> None:
        pass

    def force_flush(self, timeout_millis: int = 30_000) -> bool:
        return True


__all__ = [
    "AnalyticsSpanProcessor",
    "SpanEdge",
    "TraceRecorder",
    "TraceSummary",
]
