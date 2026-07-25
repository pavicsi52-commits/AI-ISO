"""Telemetry manager.

The primary developer-facing entry point a service actually calls,
mirroring :class:`shared_core.monitoring.manager.MonitoringManager`'s
role (Prompt 023): wires the tracer provider, tracer, sampler, and
in-process analytics recorder together behind a small, cohesive API.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass

from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.sampling import Sampler
from opentelemetry.trace import Span, Tracer

from shared_core.telemetry.analytics import TraceRecorder
from shared_core.telemetry.constants import DEFAULT_MAX_QUEUE_SIZE
from shared_core.telemetry.context import TraceContext, current_trace_context
from shared_core.telemetry.health import TelemetryHealthReport, calculate_telemetry_health
from shared_core.telemetry.provider import shutdown_tracing
from shared_core.telemetry.span import SpanType
from shared_core.telemetry.span import start_span as _start_span
from shared_core.telemetry.trace import start_root_trace as _start_root_trace


@dataclass(slots=True)
class TelemetryManager:
    """Everything a service needs to create traces and read this framework's own state."""

    service_name: str
    service_version: str
    environment: str
    tracer_provider: TracerProvider
    tracer: Tracer
    recorder: TraceRecorder
    sampler: Sampler | None = None

    @contextmanager
    def start_root_trace(self, name: str, **attributes: str) -> Iterator[Span]:
        """Start a new, parentless trace ("Distributed Tracing": an entry point)."""
        with _start_root_trace(self.tracer, name, **attributes) as span:
            yield span

    @contextmanager
    def start_span(
        self, name: str, *, span_type: SpanType | None = None, **attributes: str
    ) -> Iterator[Span]:
        """Start a span under whatever is currently active."""
        with _start_span(self.tracer, name, span_type=span_type, **attributes) as span:
            yield span

    def current_trace_context(self) -> TraceContext:
        """The current :class:`~shared_core.telemetry.context.TraceContext`."""
        return current_trace_context(
            service_name=self.service_name,
            service_version=self.service_version,
            environment=self.environment,
        )

    def health(self) -> TelemetryHealthReport:
        """This framework's own health ("HEALTH"). Best-effort.

        The OpenTelemetry SDK's ``BatchSpanProcessor`` doesn't expose a
        stable public API for dropped-span counts or live queue depth,
        so those default to their healthiest values here; a service
        wanting precise figures should wrap its own exporter/processor
        with counting instrumentation and call
        :func:`shared_core.telemetry.health.calculate_telemetry_health`
        directly with the real numbers.
        """
        sampling_rate = getattr(self.sampler, "ratio", 1.0)
        return calculate_telemetry_health(
            exporter_healthy=True,
            dropped_spans=0,
            sampling_rate=sampling_rate,
            buffer_usage=0,
            buffer_capacity=DEFAULT_MAX_QUEUE_SIZE,
            queue_length=0,
            export_latency_ms=None,
        )

    def shutdown(self) -> None:
        """Flush and shut down the tracer provider. Call once at service shutdown."""
        shutdown_tracing(self.tracer_provider)


__all__ = ["TelemetryManager"]
