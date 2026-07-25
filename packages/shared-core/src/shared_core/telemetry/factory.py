"""Enterprise Telemetry Framework factory.

Assembles the tracer provider, exporter, sampler, and analytics recorder
into one :class:`~shared_core.telemetry.manager.TelemetryManager` a
service builds exactly once at startup, from
:class:`~shared_core.config.settings.TelemetrySettings` (Prompt 013) --
mirroring :func:`shared_core.queue.factory.create_queue_framework`
(Prompt 021).
"""

from __future__ import annotations

from pathlib import Path

from opentelemetry.sdk.trace.export import BatchSpanProcessor

from shared_core.config.settings import TelemetrySettings
from shared_core.telemetry.analytics import AnalyticsSpanProcessor, TraceRecorder
from shared_core.telemetry.exporters import create_exporter
from shared_core.telemetry.manager import TelemetryManager
from shared_core.telemetry.provider import configure_tracing
from shared_core.telemetry.sampling import never_sample, probability_sampler


def create_telemetry_framework(
    settings: TelemetrySettings,
    *,
    service_version: str = "0.0.0",
    environment: str = "development",
    json_path: str | Path = "spans.jsonl",
) -> TelemetryManager:
    """Build a :class:`TelemetryManager` from Configuration Framework settings.

    ``telemetry_enabled=False`` still returns a fully working manager --
    just sampling nothing (:func:`~shared_core.telemetry.sampling.never_sample`)
    rather than requiring every caller to None-check whether telemetry is
    on before using it. ``json_path`` only matters when
    ``settings.telemetry_exporter == "json"``.
    """
    sampler = (
        probability_sampler(settings.telemetry_sample_ratio)
        if settings.telemetry_enabled
        else never_sample()
    )
    exporter = create_exporter(
        settings.telemetry_exporter,
        otlp_endpoint=settings.telemetry_otlp_endpoint,
        json_path=json_path,
    )
    recorder = TraceRecorder()
    provider = configure_tracing(
        service_name=settings.telemetry_service_name,
        service_version=service_version,
        environment=environment,
        span_processor=BatchSpanProcessor(exporter),
        sampler=sampler,
    )
    provider.add_span_processor(AnalyticsSpanProcessor(recorder))
    tracer = provider.get_tracer(settings.telemetry_service_name)
    return TelemetryManager(
        service_name=settings.telemetry_service_name,
        service_version=service_version,
        environment=environment,
        tracer_provider=provider,
        tracer=tracer,
        recorder=recorder,
        sampler=sampler,
    )


__all__ = ["create_telemetry_framework"]
