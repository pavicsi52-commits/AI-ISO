"""Middleware that logs request completion with latency and status code."""

from __future__ import annotations

import time

from shared_core.logging import get_logger
from starlette.types import ASGIApp, Message, Receive, Scope, Send

logger = get_logger("app.request")


class TimingMiddleware:
    """ASGI middleware logging method, path, status code, and latency."""

    def __init__(self, app: ASGIApp) -> None:
        self._app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self._app(scope, receive, send)
            return

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
                "request completed",
                extra={
                    "extra_fields": {
                        "method": scope.get("method"),
                        "path": scope.get("path"),
                        "status_code": status_code,
                        "latency_ms": latency_ms,
                    }
                },
            )
