"""Monitoring decorators."""

from __future__ import annotations

import time
from collections.abc import Awaitable, Callable
from functools import wraps
from typing import ParamSpec, TypeVar

from shared_core.monitoring.application import ApplicationStatistics

P = ParamSpec("P")
T = TypeVar("T")


def monitored(
    statistics: ApplicationStatistics,
) -> Callable[[Callable[P, Awaitable[T]]], Callable[P, Awaitable[T]]]:
    """Record every call to the decorated async function into *statistics*.

    Counts as a "request" (response time + request count), and as an
    exception if the call raises -- the same accounting
    :class:`~shared_core.monitoring.middleware.ApplicationMonitoringMiddleware`
    gives real HTTP traffic, for background jobs/workers that never go
    through that middleware.
    """

    def decorator(func: Callable[P, Awaitable[T]]) -> Callable[P, Awaitable[T]]:
        @wraps(func)
        async def wrapper(*args: P.args, **kwargs: P.kwargs) -> T:
            start = time.perf_counter()
            try:
                result = await func(*args, **kwargs)
            except Exception:
                statistics.record_exception()
                raise
            finally:
                response_time_ms = (time.perf_counter() - start) * 1000
                statistics.record_request(response_time_ms)
            return result

        return wrapper

    return decorator


def track_errors(
    statistics: ApplicationStatistics,
) -> Callable[[Callable[P, Awaitable[T]]], Callable[P, Awaitable[T]]]:
    """Record every exception the wrapped function raises into *statistics*, without swallowing."""

    def decorator(func: Callable[P, Awaitable[T]]) -> Callable[P, Awaitable[T]]:
        @wraps(func)
        async def wrapper(*args: P.args, **kwargs: P.kwargs) -> T:
            try:
                return await func(*args, **kwargs)
            except Exception:
                statistics.record_error()
                raise

        return wrapper

    return decorator


__all__ = ["monitored", "track_errors"]
