"""Connector telemetry.

Per docs/027_Enterprise_Connector_SDK.md.txt "TELEMETRY": Trace every
operation. Include Trace ID, Connector Name, Provider, Target,
Duration, Status, Errors. "Integrate with Prompt 024." Reuses
:func:`shared_core.telemetry.connector.trace_connector_execution`
directly (Prompt 024 already built this exact integration point)
rather than a second connector-tracing implementation. Trace ID/
Duration are automatic (OpenTelemetry's own span id/timing); this
module only adds the "Status"/"Errors" convention: every span records
``status=success`` or ``status=error`` (plus the error message), set
from *within* this module so every connector operation reports it the
same, consistent way.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from opentelemetry.trace import Tracer

from shared_core.telemetry.connector import trace_connector_execution


@asynccontextmanager
async def trace_operation(
    tracer: Tracer, connector_name: str, *, provider: str, target: str, operation: str
) -> AsyncIterator[None]:
    """Trace one connector operation ("Trace every operation")."""
    with trace_connector_execution(
        tracer, connector_name, provider=provider, target=target, operation=operation
    ) as span:
        try:
            yield
        except Exception as exc:
            span.set_attribute("status", "error")
            span.set_attribute("error", str(exc))
            raise
        else:
            span.set_attribute("status", "success")


__all__ = ["trace_operation"]
