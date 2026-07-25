"""Function-level rate limit decorator.

For HTTP-layer rate limiting, prefer
:class:`shared_core.middleware.RateLimitMiddleware`. This decorator is for
rate-limiting arbitrary async functions (e.g. outbound calls to a
third-party API) using the same underlying limiter.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from functools import wraps
from typing import Any

from shared_core.constants.http import HttpConstants
from shared_core.exceptions.rate_limit import RateLimitError
from shared_core.middleware.rate_limit import InMemoryRateLimiter


def rate_limited(
    *,
    key: str,
    max_requests: int = HttpConstants.DEFAULT_RATE_LIMIT_PER_MINUTE,
    window_seconds: float = 60.0,
) -> Callable[[Callable[..., Awaitable[Any]]], Callable[..., Awaitable[Any]]]:
    """Rate-limit calls to the decorated async function under a shared ``key``."""
    limiter = InMemoryRateLimiter(max_requests=max_requests, window_seconds=window_seconds)

    def decorator(func: Callable[..., Awaitable[Any]]) -> Callable[..., Awaitable[Any]]:
        @wraps(func)
        async def wrapper(*args: Any, **kwargs: Any) -> Any:
            if not limiter.allow(key):
                raise RateLimitError(f"Rate limit exceeded for '{key}'.")
            return await func(*args, **kwargs)

        return wrapper

    return decorator
