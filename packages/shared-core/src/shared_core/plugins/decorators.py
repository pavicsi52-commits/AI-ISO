"""Plugin registration and operation decorators.

Mark-now, wire-later helpers: ``@hook(hook_name)`` attaches a hook name
to an async callback (paired with
:class:`~shared_core.plugins.hooks.HookRegistry`, the same "mark now,
wire later" pattern as :mod:`shared_core.workflow.decorators`'s
``@node_handler``); ``@extension(namespace, category)`` attaches an
extension target to a contributed value (paired with
:class:`~shared_core.plugins.extensions.NamespacedExtensions`);
``@retryable``/``@timed`` wrap a single async function in this
framework's own retry/metrics primitives without needing the full
middleware chain from :mod:`shared_core.plugins.middleware`.
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from functools import wraps
from typing import ParamSpec, TypeVar

from shared_core.plugins import metrics as plugin_metrics
from shared_core.queue.retry import RetryPolicy

P = ParamSpec("P")
T = TypeVar("T")

_HOOK_NAME_ATTR = "__plugin_hook_name__"
_EXTENSION_TARGET_ATTR = "__plugin_extension_target__"
_ATTEMPT_START = 1


def hook(hook_name: str) -> Callable[[Callable[P, Awaitable[T]]], Callable[P, Awaitable[T]]]:
    """Mark an async callback with the hook name it handles ("@hook")."""

    def decorator(func: Callable[P, Awaitable[T]]) -> Callable[P, Awaitable[T]]:
        setattr(func, _HOOK_NAME_ATTR, hook_name)
        return func

    return decorator


def get_hook_name(func: Callable[..., object]) -> str | None:
    """Return the hook name *func* was decorated with, or ``None`` if it wasn't."""
    name = getattr(func, _HOOK_NAME_ATTR, None)
    return name if isinstance(name, str) else None


def extension(namespace: str, category: str) -> Callable[[Callable[P, T]], Callable[P, T]]:
    """Mark a function as one namespace/category extension contribution ("@extension")."""

    def decorator(func: Callable[P, T]) -> Callable[P, T]:
        setattr(func, _EXTENSION_TARGET_ATTR, (namespace, category))
        return func

    return decorator


def get_extension_target(func: Callable[..., object]) -> tuple[str, str] | None:
    """Return the ``(namespace, category)`` *func* was decorated with, or ``None``."""
    target = getattr(func, _EXTENSION_TARGET_ATTR, None)
    return target if isinstance(target, tuple) else None


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


def timed(plugin_id: str) -> Callable[[Callable[P, Awaitable[T]]], Callable[P, Awaitable[T]]]:
    """Wrap an async function to record its execution time ("@timed")."""

    def decorator(func: Callable[P, Awaitable[T]]) -> Callable[P, Awaitable[T]]:
        @wraps(func)
        async def wrapper(*args: P.args, **kwargs: P.kwargs) -> T:
            with plugin_metrics.measure_execution(plugin_id):
                return await func(*args, **kwargs)

        return wrapper

    return decorator


__all__ = [
    "extension",
    "get_extension_target",
    "get_hook_name",
    "hook",
    "retryable",
    "timed",
]
