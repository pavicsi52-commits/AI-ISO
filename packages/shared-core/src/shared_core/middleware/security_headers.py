"""Security headers middleware.

Basic header set from docs/012_Shared_Core_Framework.md.txt "MIDDLEWARE".
docs/017_Enterprise_Security_Framework.md.txt makes these fully configurable
per environment.
"""

from __future__ import annotations

from starlette.types import ASGIApp, Message, Receive, Scope, Send

_SECURITY_HEADERS: tuple[tuple[str, str], ...] = (
    ("strict-transport-security", "max-age=63072000; includeSubDomains"),
    ("x-frame-options", "DENY"),
    ("x-content-type-options", "nosniff"),
    ("referrer-policy", "strict-origin-when-cross-origin"),
    ("permissions-policy", "geolocation=(), camera=(), microphone=()"),
    ("x-xss-protection", "0"),
)


class SecurityHeadersMiddleware:
    """ASGI middleware adding standard security response headers."""

    def __init__(self, app: ASGIApp) -> None:
        self._app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self._app(scope, receive, send)
            return

        async def add_headers(message: Message) -> None:
            if message["type"] == "http.response.start":
                headers = message.setdefault("headers", [])
                headers.extend((name.encode(), value.encode()) for name, value in _SECURITY_HEADERS)
            await send(message)

        await self._app(scope, receive, add_headers)
