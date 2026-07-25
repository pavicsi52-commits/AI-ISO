"""Request validation middleware.

Runs Layer 3 ("API Validation") automatically for every request --
required headers and a body-size cap -- before it reaches a route
handler. Schema validation (Layer 4) is already enforced by FastAPI/
Pydantic on every typed request body; this middleware covers what
Pydantic doesn't (headers, raw body size) per docs/016 "REQUEST
VALIDATION".
"""

from __future__ import annotations

from collections.abc import Sequence

from starlette.requests import Request
from starlette.types import ASGIApp, Receive, Scope, Send

from shared_core.exceptions.validation import ValidationError
from shared_core.validation.rules.request import validate_body_size, validate_headers


class RequestValidationMiddleware:
    """ASGI middleware enforcing required headers and a request body size cap."""

    def __init__(
        self,
        app: ASGIApp,
        *,
        required_headers: Sequence[str] = (),
        max_body_bytes: int = 100 * 1024 * 1024,
    ) -> None:
        self._app = app
        self._required_headers = required_headers
        self._max_body_bytes = max_body_bytes

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self._app(scope, receive, send)
            return

        request = Request(scope, receive=receive)

        headers_result = validate_headers(dict(request.headers), required=self._required_headers)
        if not headers_result.valid:
            raise ValidationError("Request validation failed.", details=headers_result.errors)

        content_length = request.headers.get("content-length")
        size_result = validate_body_size(
            int(content_length) if content_length is not None else None,
            max_bytes=self._max_body_bytes,
        )
        if not size_result.valid:
            raise ValidationError("Request validation failed.", details=size_result.errors)

        await self._app(scope, receive, send)
