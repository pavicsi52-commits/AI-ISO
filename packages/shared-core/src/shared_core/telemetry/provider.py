"""Tracer provider configuration.

Configures a global :class:`~opentelemetry.sdk.trace.TracerProvider`
once per process, per
docs/024_Enterprise_Telemetry_Framework.md.txt "OPENTELEMETRY": OpenTelemetry
SDK integration following OpenTelemetry semantic conventions
(``service.name``/``service.version``/``deployment.environment``/
``host.name`` resource attributes).

Was Prompt 012's baseline ``tracing.py`` (``configure_tracing``); split
along this prompt's own file boundaries -- provider/exporter setup here,
tracer/root-trace helpers in :mod:`shared_core.telemetry.trace`, span
helpers in :mod:`shared_core.telemetry.span`.
"""

from __future__ import annotations

import socket

from opentelemetry import trace
from opentelemetry.sdk.resources import (
    DEPLOYMENT_ENVIRONMENT,
    HOST_NAME,
    SERVICE_NAME,
    SERVICE_VERSION,
    Resource,
)
from opentelemetry.sdk.trace import SpanProcessor, TracerProvider
from opentelemetry.sdk.trace.sampling import Sampler


def build_resource(
    *, service_name: str, service_version: str = "0.0.0", environment: str = "development"
) -> Resource:
    """Build the OpenTelemetry resource attached to every span this process emits."""
    return Resource.create(
        {
            SERVICE_NAME: service_name,
            SERVICE_VERSION: service_version,
            DEPLOYMENT_ENVIRONMENT: environment,
            HOST_NAME: socket.gethostname(),
        }
    )


def configure_tracing(
    *,
    service_name: str,
    service_version: str = "0.0.0",
    environment: str = "development",
    span_processor: SpanProcessor,
    sampler: Sampler | None = None,
) -> TracerProvider:
    """Configure and install the global tracer provider for this process.

    Args:
        service_name: Attached to every span as the ``service.name`` resource.
        service_version: Attached as ``service.version``.
        environment: Attached as ``deployment.environment``.
        span_processor: Owns exporting finished spans -- typically a
            :class:`~opentelemetry.sdk.trace.export.BatchSpanProcessor`
            wrapping whatever :mod:`shared_core.telemetry.exporters`
            exporter this service is configured to use.
        sampler: The sampling strategy (see
            :mod:`shared_core.telemetry.sampling`); defaults to the
            OpenTelemetry SDK's own default (always-on, parent-based)
            when omitted.
    """
    resource = build_resource(
        service_name=service_name, service_version=service_version, environment=environment
    )
    provider = TracerProvider(resource=resource, sampler=sampler)
    provider.add_span_processor(span_processor)
    trace.set_tracer_provider(provider)
    return provider


def shutdown_tracing(provider: TracerProvider) -> None:
    """Flush and shut down every span processor on *provider*.

    Call once at service shutdown so buffered spans aren't lost.
    """
    provider.shutdown()


__all__ = ["build_resource", "configure_tracing", "shutdown_tracing"]
