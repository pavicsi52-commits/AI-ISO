"""Node handler registration and operation decorators.

Mark-now, wire-later helpers: ``@node_handler(node_type)`` attaches a
:class:`~shared_core.workflow.nodes.NodeType` to an async handler
function (paired with
:class:`~shared_core.workflow.executor.NodeHandlerRegistry`, the same
"mark now, wire later" pattern as
:mod:`shared_core.connectors.decorators`'s ``@connector``);
``@retryable``/``@timed`` wrap a single async function in this SDK's
own retry/metrics primitives without needing the full engine.
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from functools import wraps
from typing import ParamSpec, TypeVar

from shared_core.workflow import metrics as workflow_metrics
from shared_core.workflow.nodes import NodeType
from shared_core.workflow.retry import workflow_retry_policy

P = ParamSpec("P")
T = TypeVar("T")

_NODE_TYPE_ATTR = "__workflow_node_type__"
_ATTEMPT_START = 1


def node_handler(
    node_type: NodeType,
) -> Callable[[Callable[P, Awaitable[T]]], Callable[P, Awaitable[T]]]:
    """Mark an async handler with the :class:`NodeType` it executes ("@node_handler")."""

    def decorator(func: Callable[P, Awaitable[T]]) -> Callable[P, Awaitable[T]]:
        setattr(func, _NODE_TYPE_ATTR, node_type)
        return func

    return decorator


def get_node_type(func: Callable[..., object]) -> NodeType | None:
    """Return the :class:`NodeType` *func* was decorated with, or ``None`` if it wasn't."""
    node_type = getattr(func, _NODE_TYPE_ATTR, None)
    return node_type if isinstance(node_type, NodeType) else None


def retryable(
    *, max_attempts: int = 3
) -> Callable[[Callable[P, Awaitable[T]]], Callable[P, Awaitable[T]]]:
    """Wrap an async function with retry-with-backoff ("@retryable")."""
    policy = workflow_retry_policy()

    def decorator(func: Callable[P, Awaitable[T]]) -> Callable[P, Awaitable[T]]:
        @wraps(func)
        async def wrapper(*args: P.args, **kwargs: P.kwargs) -> T:
            last_error: Exception = RuntimeError("retryable() ran zero attempts.")
            for attempt in range(_ATTEMPT_START, max_attempts + 1):
                try:
                    return await func(*args, **kwargs)
                except Exception as exc:
                    last_error = exc
                    is_final_attempt = attempt == max_attempts
                    if not policy.classify(exc) or is_final_attempt:
                        break
                    await asyncio.sleep(policy.delay_for(attempt))
            raise last_error

        return wrapper

    return decorator


def timed(
    workflow_id: str, node_type: str
) -> Callable[[Callable[P, Awaitable[T]]], Callable[P, Awaitable[T]]]:
    """Wrap an async function to record its task duration ("@timed")."""

    def decorator(func: Callable[P, Awaitable[T]]) -> Callable[P, Awaitable[T]]:
        @wraps(func)
        async def wrapper(*args: P.args, **kwargs: P.kwargs) -> T:
            with workflow_metrics.measure_task(workflow_id, node_type):
                return await func(*args, **kwargs)

        return wrapper

    return decorator


__all__ = ["get_node_type", "node_handler", "retryable", "timed"]
