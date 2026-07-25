"""Rate limiting middleware.

In-memory, single-process sliding window limiter — sufficient for local
development and single-replica deployments. Multi-replica deployments must
use the Redis-backed limiter in docs/019_Enterprise_Cache_Framework.md.txt
(``shared_core.cache``) once that framework is wired in.
"""

from __future__ import annotations

import time
from collections import defaultdict, deque

from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Receive, Scope, Send

from shared_core.constants.http import HttpConstants


class InMemoryRateLimiter:
    """Sliding-window rate limiter keyed by an arbitrary string (e.g. client IP)."""

    def __init__(self, *, max_requests: int, window_seconds: float) -> None:
        self._max_requests = max_requests
        self._window_seconds = window_seconds
        self._hits: dict[str, deque[float]] = defaultdict(deque)

    def allow(self, key: str) -> bool:
        """Return whether a request identified by ``key`` is within limits."""
        now = time.monotonic()
        window_start = now - self._window_seconds
        hits = self._hits[key]

        while hits and hits[0] < window_start:
            hits.popleft()

        if len(hits) >= self._max_requests:
            return False

        hits.append(now)
        return True


class RateLimitMiddleware:
    """ASGI middleware enforcing a per-client-IP rate limit."""

    def __init__(
        self,
        app: ASGIApp,
        *,
        max_requests: int = HttpConstants.DEFAULT_RATE_LIMIT_PER_MINUTE,
        window_seconds: float = 60.0,
    ) -> None:
        self._app = app
        self._limiter = InMemoryRateLimiter(
            max_requests=max_requests, window_seconds=window_seconds
        )

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self._app(scope, receive, send)
            return

        request = Request(scope, receive=receive)
        client_key = request.client.host if request.client else "unknown"

        if not self._limiter.allow(client_key):
            response = JSONResponse(
                status_code=429,
                content={
                    "success": False,
                    "message": "Rate limit exceeded.",
                    "error": {"code": "AIIOS-RATE-0001", "details": []},
                },
            )
            await response(scope, receive, send)
            return

        await self._app(scope, receive, send)
