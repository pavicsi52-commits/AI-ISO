"""Request/response logging middleware.

Per docs/014_Enterprise_Logging_Framework.md.txt "REQUEST LOGGING": logs
the incoming request and outgoing response, execution time, payload size,
and status code, with headers -- safe ones only, never
``Authorization``/``Cookie``/API keys. Binds
:mod:`shared_core.logging.request_context` for the duration of the request
so every log line emitted while handling it automatically carries
method/url/ip_address/user_agent, not just the two this middleware emits
directly.
"""

from __future__ import annotations

import time

from starlette.requests import Request
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from shared_core.logging.logger import get_logger
from shared_core.logging.request_context import (
    bind_request_log_context,
    reset_request_log_context,
)

logger = get_logger("shared_core.request")

_UNSAFE_HEADERS = frozenset(
    {"authorization", "cookie", "set-cookie", "x-api-key", "proxy-authorization"}
)


def _safe_headers(request: Request) -> dict[str, str]:
    """Every request header except ones that could carry credentials."""
    return {
        name: value
        for name, value in request.headers.items()
        if name.lower() not in _UNSAFE_HEADERS
    }


class RequestLoggingMiddleware:
    """ASGI middleware logging the full request/response lifecycle."""

    def __init__(self, app: ASGIApp) -> None:
        self._app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self._app(scope, receive, send)
            return

        request = Request(scope, receive=receive)
        client = request.client
        bind_request_log_context(
            method=request.method,
            url=str(request.url),
            ip_address=client.host if client else None,
            user_agent=request.headers.get("user-agent"),
        )

        logger.info(
            "request.started",
            extra={
                "extra_fields": {
                    "headers": _safe_headers(request),
                    "payload_size": request.headers.get("content-length"),
                }
            },
        )

        start = time.perf_counter()
        status_code = 500

        async def capture_status(message: Message) -> None:
            nonlocal status_code
            if message["type"] == "http.response.start":
                status_code = message["status"]
            await send(message)

        try:
            await self._app(scope, receive, capture_status)
        finally:
            latency_ms = round((time.perf_counter() - start) * 1000, 2)
            logger.info(
                "request.completed",
                extra={"extra_fields": {"status_code": status_code, "latency_ms": latency_ms}},
            )
            reset_request_log_context()
