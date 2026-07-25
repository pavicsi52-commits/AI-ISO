"""Telemetry decorators.

Per docs/024_Enterprise_Telemetry_Framework.md.txt "DECORATORS":
``@trace``, ``@span``, ``@measure``, ``@profile``, ``@track_database``,
``@track_cache``, ``@track_queue``, ``@track_storage``,
``@track_connector``, ``@track_plugin``, ``@track_workflow``,
``@track_automation``, ``@track_validation``, ``@track_ai``.

Async-only, matching this codebase's async-first convention for I/O
operations (the same choice
:mod:`shared_core.monitoring.decorators`'s ``@monitored``/``@track_errors``
made) -- every operation these decorators instrument (a database query,
a cache call, an AI request, ...) is already async everywhere in
shared-core. The ``@track_*`` decorators name each span after the
wrapped function itself (``operation=func.__name__``); a caller wanting
a specific, hand-chosen name/table/key/etc. should use the underlying
context manager (:mod:`shared_core.telemetry.database`, ``.cache``, ...)
directly instead.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from functools import wraps
from typing import ParamSpec, TypeVar

from opentelemetry.trace import Tracer
from prometheus_client import Histogram

from shared_core.telemetry.ai import trace_ai_request
from shared_core.telemetry.automation import trace_automation_step
from shared_core.telemetry.cache import trace_cache_access
from shared_core.telemetry.connector import trace_connector_execution
from shared_core.telemetry.database import trace_database_query
from shared_core.telemetry.metrics import observe_with_trace_exemplar
from shared_core.telemetry.plugin import trace_plugin_execution
from shared_core.telemetry.profiling import DeepProfile, measure_duration_ms
from shared_core.telemetry.queue import trace_queue_publish
from shared_core.telemetry.span import SpanType, start_span
from shared_core.telemetry.storage import trace_file_upload
from shared_core.telemetry.trace import start_root_trace
from shared_core.telemetry.validation import trace_validation_step
from shared_core.telemetry.workflow import trace_workflow_step

P = ParamSpec("P")
T = TypeVar("T")


def trace(
    tracer: Tracer, *, name: str | None = None
) -> Callable[[Callable[P, Awaitable[T]]], Callable[P, Awaitable[T]]]:
    """Wrap a function in its own root trace ("@trace"). No parent -- a genuine entry point."""

    def decorator(func: Callable[P, Awaitable[T]]) -> Callable[P, Awaitable[T]]:
        span_name = name or func.__name__

        @wraps(func)
        async def wrapper(*args: P.args, **kwargs: P.kwargs) -> T:
            with start_root_trace(tracer, span_name):
                return await func(*args, **kwargs)

        return wrapper

    return decorator


def span(
    tracer: Tracer, *, name: str | None = None, span_type: SpanType | None = None
) -> Callable[[Callable[P, Awaitable[T]]], Callable[P, Awaitable[T]]]:
    """Wrap a function in a child span ("@span"), attached under whatever is currently active."""

    def decorator(func: Callable[P, Awaitable[T]]) -> Callable[P, Awaitable[T]]:
        span_name = name or func.__name__

        @wraps(func)
        async def wrapper(*args: P.args, **kwargs: P.kwargs) -> T:
            with start_span(tracer, span_name, span_type=span_type):
                return await func(*args, **kwargs)

        return wrapper

    return decorator


def measure(
    histogram: Histogram, **labels: str
) -> Callable[[Callable[P, Awaitable[T]]], Callable[P, Awaitable[T]]]:
    """Time a function's execution into *histogram*, correlated with the current trace."""

    def decorator(func: Callable[P, Awaitable[T]]) -> Callable[P, Awaitable[T]]:
        @wraps(func)
        async def wrapper(*args: P.args, **kwargs: P.kwargs) -> T:
            with measure_duration_ms(func.__name__) as result:
                value = await func(*args, **kwargs)
            observe_with_trace_exemplar(histogram, result.duration_ms / 1000, **labels)
            return value

        return wrapper

    return decorator


def profile(
    *, top_n: int = 20
) -> Callable[[Callable[P, Awaitable[T]]], Callable[P, Awaitable[tuple[T, str]]]]:
    """Deep-profile a function's execution with :mod:`cProfile` ("@profile").

    Returns ``(result, stats_text)`` instead of just the wrapped
    function's own return value -- deliberately opt-in and visible in
    the call site, since deep profiling is expensive and this framework
    must have "minimal runtime overhead" as its default.
    """

    def decorator(func: Callable[P, Awaitable[T]]) -> Callable[P, Awaitable[tuple[T, str]]]:
        @wraps(func)
        async def wrapper(*args: P.args, **kwargs: P.kwargs) -> tuple[T, str]:
            with DeepProfile() as deep_profile:
                result = await func(*args, **kwargs)
            return result, deep_profile.stats(top_n=top_n)

        return wrapper

    return decorator


def track_database(
    tracer: Tracer, *, table: str | None = None
) -> Callable[[Callable[P, Awaitable[T]]], Callable[P, Awaitable[T]]]:
    """Wrap a function in a Database Query span ("@track_database")."""

    def decorator(func: Callable[P, Awaitable[T]]) -> Callable[P, Awaitable[T]]:
        @wraps(func)
        async def wrapper(*args: P.args, **kwargs: P.kwargs) -> T:
            with trace_database_query(tracer, func.__name__, table=table):
                return await func(*args, **kwargs)

        return wrapper

    return decorator


def track_cache(
    tracer: Tracer,
) -> Callable[[Callable[P, Awaitable[T]]], Callable[P, Awaitable[T]]]:
    """Wrap a function in a Cache Access span ("@track_cache")."""

    def decorator(func: Callable[P, Awaitable[T]]) -> Callable[P, Awaitable[T]]:
        @wraps(func)
        async def wrapper(*args: P.args, **kwargs: P.kwargs) -> T:
            with trace_cache_access(tracer, func.__name__):
                return await func(*args, **kwargs)

        return wrapper

    return decorator


def track_queue(
    tracer: Tracer, queue_name: str
) -> Callable[[Callable[P, Awaitable[T]]], Callable[P, Awaitable[T]]]:
    """Wrap a function in a Queue Publish span ("@track_queue")."""

    def decorator(func: Callable[P, Awaitable[T]]) -> Callable[P, Awaitable[T]]:
        @wraps(func)
        async def wrapper(*args: P.args, **kwargs: P.kwargs) -> T:
            with trace_queue_publish(tracer, queue_name):
                return await func(*args, **kwargs)

        return wrapper

    return decorator


def track_storage(
    tracer: Tracer,
) -> Callable[[Callable[P, Awaitable[T]]], Callable[P, Awaitable[T]]]:
    """Wrap a function in a File Upload span ("@track_storage")."""

    def decorator(func: Callable[P, Awaitable[T]]) -> Callable[P, Awaitable[T]]:
        @wraps(func)
        async def wrapper(*args: P.args, **kwargs: P.kwargs) -> T:
            with trace_file_upload(tracer, func.__name__):
                return await func(*args, **kwargs)

        return wrapper

    return decorator


def track_connector(
    tracer: Tracer, connector_name: str
) -> Callable[[Callable[P, Awaitable[T]]], Callable[P, Awaitable[T]]]:
    """Wrap a function in a Connector Execution span ("@track_connector")."""

    def decorator(func: Callable[P, Awaitable[T]]) -> Callable[P, Awaitable[T]]:
        @wraps(func)
        async def wrapper(*args: P.args, **kwargs: P.kwargs) -> T:
            with trace_connector_execution(tracer, connector_name):
                return await func(*args, **kwargs)

        return wrapper

    return decorator


def track_plugin(
    tracer: Tracer, plugin_name: str
) -> Callable[[Callable[P, Awaitable[T]]], Callable[P, Awaitable[T]]]:
    """Wrap a function in a Plugin Execution span ("@track_plugin")."""

    def decorator(func: Callable[P, Awaitable[T]]) -> Callable[P, Awaitable[T]]:
        @wraps(func)
        async def wrapper(*args: P.args, **kwargs: P.kwargs) -> T:
            with trace_plugin_execution(tracer, plugin_name):
                return await func(*args, **kwargs)

        return wrapper

    return decorator


def track_workflow(
    tracer: Tracer, workflow_name: str
) -> Callable[[Callable[P, Awaitable[T]]], Callable[P, Awaitable[T]]]:
    """Wrap a function in a Workflow Step span ("@track_workflow")."""

    def decorator(func: Callable[P, Awaitable[T]]) -> Callable[P, Awaitable[T]]:
        @wraps(func)
        async def wrapper(*args: P.args, **kwargs: P.kwargs) -> T:
            with trace_workflow_step(tracer, workflow_name, func.__name__):
                return await func(*args, **kwargs)

        return wrapper

    return decorator


def track_automation(
    tracer: Tracer, automation_name: str
) -> Callable[[Callable[P, Awaitable[T]]], Callable[P, Awaitable[T]]]:
    """Wrap a function in an Automation Step span ("@track_automation")."""

    def decorator(func: Callable[P, Awaitable[T]]) -> Callable[P, Awaitable[T]]:
        @wraps(func)
        async def wrapper(*args: P.args, **kwargs: P.kwargs) -> T:
            with trace_automation_step(tracer, automation_name, func.__name__):
                return await func(*args, **kwargs)

        return wrapper

    return decorator


def track_validation(
    tracer: Tracer,
) -> Callable[[Callable[P, Awaitable[T]]], Callable[P, Awaitable[T]]]:
    """Wrap a function in a Validation Step span ("@track_validation")."""

    def decorator(func: Callable[P, Awaitable[T]]) -> Callable[P, Awaitable[T]]:
        @wraps(func)
        async def wrapper(*args: P.args, **kwargs: P.kwargs) -> T:
            with trace_validation_step(tracer, func.__name__):
                return await func(*args, **kwargs)

        return wrapper

    return decorator


def track_ai(
    tracer: Tracer, provider: str
) -> Callable[[Callable[P, Awaitable[T]]], Callable[P, Awaitable[T]]]:
    """Wrap a function in an AI Request span ("@track_ai")."""

    def decorator(func: Callable[P, Awaitable[T]]) -> Callable[P, Awaitable[T]]:
        @wraps(func)
        async def wrapper(*args: P.args, **kwargs: P.kwargs) -> T:
            with trace_ai_request(tracer, provider):
                return await func(*args, **kwargs)

        return wrapper

    return decorator


__all__ = [
    "measure",
    "profile",
    "span",
    "trace",
    "track_ai",
    "track_automation",
    "track_cache",
    "track_connector",
    "track_database",
    "track_plugin",
    "track_queue",
    "track_storage",
    "track_validation",
    "track_workflow",
]
