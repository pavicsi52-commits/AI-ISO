"""Connector registration and operation decorators.

Mark-now, wire-later helpers: ``@connector(provider_name)`` attaches a
provider name to a :class:`~shared_core.connectors.base.BaseConnector`
subclass (paired with
:class:`~shared_core.connectors.registry.ConnectorRegistry`, the same
"mark now, wire later" pattern as :mod:`shared_core.queue.decorators`'s
``@job``); ``@retryable``/``@timed`` wrap a single async function in
this SDK's own retry/metrics primitives without needing the full
middleware chain from :mod:`shared_core.connectors.middleware`.
"""

from __future__ import annotations

import asyncio
import time
from collections.abc import Awaitable, Callable
from functools import wraps
from typing import ParamSpec, TypeVar

from shared_core.connectors.base import BaseConnector
from shared_core.connectors.metrics import record_failure, record_success
from shared_core.queue.retry import RetryPolicy

P = ParamSpec("P")
T = TypeVar("T")

_PROVIDER_NAME_ATTR = "__connector_provider_name__"
_ATTEMPT_START = 1

ConnectorClass = type[BaseConnector]


def connector(provider_name: str) -> Callable[[ConnectorClass], ConnectorClass]:
    """Mark a :class:`BaseConnector` subclass with its provider name ("@connector")."""

    def decorator(cls: ConnectorClass) -> ConnectorClass:
        setattr(cls, _PROVIDER_NAME_ATTR, provider_name)
        cls.provider_name = provider_name
        return cls

    return decorator


def get_provider_name(cls: ConnectorClass) -> str | None:
    """Return the provider name *cls* was decorated with, or ``None`` if it wasn't."""
    name = getattr(cls, _PROVIDER_NAME_ATTR, None)
    return name if isinstance(name, str) else None


def retryable(
    *, max_attempts: int = 3
) -> Callable[[Callable[P, Awaitable[T]]], Callable[P, Awaitable[T]]]:
    """Wrap an async function with retry-with-backoff ("@retryable")."""
    policy = RetryPolicy(max_attempts=max_attempts)

    def decorator(func: Callable[P, Awaitable[T]]) -> Callable[P, Awaitable[T]]:
        @wraps(func)
        async def wrapper(*args: P.args, **kwargs: P.kwargs) -> T:
            last_error: Exception = RuntimeError("retryable() ran zero attempts.")
            for attempt in range(_ATTEMPT_START, policy.max_attempts + 1):
                try:
                    return await func(*args, **kwargs)
                except Exception as exc:
                    last_error = exc
                    is_final_attempt = attempt == policy.max_attempts
                    if not policy.classify(exc) or is_final_attempt:
                        break
                    await asyncio.sleep(policy.delay_for(attempt))
            raise last_error

        return wrapper

    return decorator


def timed(provider: str) -> Callable[[Callable[P, Awaitable[T]]], Callable[P, Awaitable[T]]]:
    """Wrap an async function to record success/failure metrics for *provider* ("@timed")."""

    def decorator(func: Callable[P, Awaitable[T]]) -> Callable[P, Awaitable[T]]:
        @wraps(func)
        async def wrapper(*args: P.args, **kwargs: P.kwargs) -> T:
            start = time.perf_counter()
            try:
                result = await func(*args, **kwargs)
            except Exception:
                record_failure(provider)
                raise
            record_success(provider, latency_seconds=time.perf_counter() - start)
            return result

        return wrapper

    return decorator


__all__ = ["ConnectorClass", "connector", "get_provider_name", "retryable", "timed"]
