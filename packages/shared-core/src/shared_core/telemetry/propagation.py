"""Context propagation.

Per docs/024_Enterprise_Telemetry_Framework.md.txt "CONTEXT PROPAGATION":
HTTP Headers, Queue Messages, Background Workers, Scheduler Jobs, Async
Tasks, WebSockets ("Future gRPC Metadata" is explicitly out of scope
until a gRPC transport exists). Built on the OpenTelemetry SDK's own W3C
Trace Context propagator (``traceparent``/``tracestate`` headers) rather
than a bespoke format, so traces stay interoperable with any standard
OTel-instrumented system this platform talks to.

A single ``dict[str, str]`` carrier covers every one of the listed
transports: HTTP headers, a queue message's header dict, a scheduler
job's stored metadata, and a WebSocket handshake's headers are all
already dict-shaped (or trivially converted to one) in this codebase.
"""

from __future__ import annotations

from opentelemetry import context as otel_context
from opentelemetry import propagate

from shared_core.telemetry.exceptions import PropagationError

_Carrier = dict[str, str]


def inject_context(carrier: _Carrier | None = None) -> _Carrier:
    """Inject the current trace context into *carrier* (or a new dict) and return it.

    Used at every outbound boundary this service crosses: an HTTP client
    call, a queue publish, a scheduled job's stored payload.
    """
    target: _Carrier = carrier if carrier is not None else {}
    try:
        propagate.inject(target)
    except Exception as exc:
        raise PropagationError(f"Failed to inject trace context: {exc}") from exc
    return target


def extract_context(carrier: _Carrier) -> otel_context.Context:
    """Extract a trace context from *carrier*, to attach with :func:`use_context`.

    Used at every inbound boundary: an incoming HTTP request's headers, a
    consumed queue message's headers, a scheduler job's stored metadata.
    """
    try:
        return propagate.extract(carrier)
    except Exception as exc:
        raise PropagationError(f"Failed to extract trace context: {exc}") from exc


def use_context(context: otel_context.Context) -> object:
    """Attach *context* as current, returning a token for :func:`restore_context`."""
    return otel_context.attach(context)


def restore_context(token: object) -> None:
    """Detach a context previously attached with :func:`use_context`."""
    otel_context.detach(token)  # type: ignore[arg-type]


__all__ = ["extract_context", "inject_context", "restore_context", "use_context"]
