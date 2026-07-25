"""Request ID / Correlation ID middleware.

Assigns (or honors caller-supplied) request and correlation IDs, binds them
to the structured-logging context, and echoes them back as response
headers, per docs/006_API_Design_Master.md.txt.
"""

from __future__ import annotations

import uuid
from collections.abc import Awaitable, Callable

from starlette.requests import Request
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from shared_core.constants.http import HttpConstants
from shared_core.logging.context import bind_log_context, reset_log_context


class RequestContextMiddleware:
    """ASGI middleware binding request/correlation IDs to the log context."""

    def __init__(self, app: ASGIApp) -> None:
        self._app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self._app(scope, receive, send)
            return

        request = Request(scope, receive=receive)
        request_id = request.headers.get(HttpConstants.HEADER_REQUEST_ID) or str(uuid.uuid4())
        correlation_id = request.headers.get(HttpConstants.HEADER_CORRELATION_ID) or request_id
        bind_log_context(request_id=request_id, correlation_id=correlation_id)

        send_with_headers = _inject_headers(send, request_id, correlation_id)

        try:
            await self._app(scope, receive, send_with_headers)
        finally:
            reset_log_context()


def _inject_headers(
    send: Send, request_id: str, correlation_id: str
) -> Callable[[Message], Awaitable[None]]:
    async def wrapped(message: Message) -> None:
        if message["type"] == "http.response.start":
            headers = message.setdefault("headers", [])
            headers.append((HttpConstants.HEADER_REQUEST_ID.lower().encode(), request_id.encode()))
            headers.append(
                (HttpConstants.HEADER_CORRELATION_ID.lower().encode(), correlation_id.encode())
            )
        await send(message)

    return wrapped
