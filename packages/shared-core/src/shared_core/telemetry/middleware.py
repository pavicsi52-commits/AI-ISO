"""HTTP request root trace middleware.

Per docs/024_Enterprise_Telemetry_Framework.md.txt "MIDDLEWARE":
"Automatically create root traces for" HTTP Requests. Raw ASGI, matching
:class:`shared_core.middleware.timing.TimingMiddleware`'s exact shape
(Prompt 012) rather than Starlette's ``BaseHTTPMiddleware``. Also covers
"CONTEXT PROPAGATION": HTTP Headers -- an inbound ``traceparent`` header
(e.g. from an upstream gateway) is extracted first, so this service's
span continues that trace instead of starting an unrelated one.
"""

from __future__ import annotations

from opentelemetry.trace import StatusCode, Tracer
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from shared_core.telemetry.logs import correlate_logs_with_span
from shared_core.telemetry.propagation import extract_context, restore_context, use_context
from shared_core.telemetry.request import tag_span_with_request_ids
from shared_core.telemetry.span import SpanType, start_span

_HTTP_SERVER_ERROR_STATUS: int = 500


class TracingMiddleware:
    """ASGI middleware starting one root (or propagation-continued) span per HTTP request."""

    def __init__(self, app: ASGIApp, *, tracer: Tracer) -> None:
        self._app = app
        self._tracer = tracer

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self._app(scope, receive, send)
            return

        carrier = {
            key.decode("latin-1"): value.decode("latin-1")
            for key, value in scope.get("headers", [])
        }
        token = use_context(extract_context(carrier))
        status_code = _HTTP_SERVER_ERROR_STATUS

        async def capture_status(message: Message) -> None:
            nonlocal status_code
            if message["type"] == "http.response.start":
                status_code = message["status"]
            await send(message)

        method = scope.get("method", "")
        path = scope.get("path", "")
        try:
            with start_span(
                self._tracer,
                f"{method} {path}",
                span_type=SpanType.HTTP_REQUEST,
                **{"http.method": method, "http.route": path},
            ) as span:
                tag_span_with_request_ids(span)
                correlate_logs_with_span(span)
                try:
                    await self._app(scope, receive, capture_status)
                except Exception:
                    span.set_status(StatusCode.ERROR)
                    raise
                finally:
                    span.set_attribute("http.status_code", status_code)
                    if status_code >= _HTTP_SERVER_ERROR_STATUS:
                        span.set_status(StatusCode.ERROR)
        finally:
            restore_context(token)


__all__ = ["TracingMiddleware"]
