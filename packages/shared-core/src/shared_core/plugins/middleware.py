"""Execution middleware.

Per docs/029_Enterprise_Plugin_Framework.md.txt "SECURITY": Permission
Enforcement, Sandbox Isolation, RBAC Validation, Audit Every Operation.
A middleware chain generic over *any* plugin operation (initialize,
start, stop, a hook callback, an extension invocation, ...) rather than
one method's exact signature -- the same ``apply_middleware``/``_bind``
chain shape as :mod:`shared_core.workflow.middleware`/
:mod:`shared_core.connectors.middleware`, parameterized so it can wrap
any of them identically.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import TypeVar

from opentelemetry.trace import Tracer

from shared_core.logging.logger import get_logger
from shared_core.plugins import audit as plugin_audit
from shared_core.plugins import metrics as plugin_metrics
from shared_core.plugins.permissions import PermissionRegistry, PluginPermission
from shared_core.plugins.sandbox import PluginSandbox
from shared_core.plugins.telemetry import trace_plugin_execution

logger = get_logger("shared_core.plugins")

T = TypeVar("T")


@dataclass(frozen=True, slots=True)
class PluginOperationContext:
    """Identifies one plugin operation a middleware chain wraps."""

    plugin_id: str
    operation: str
    required_permission: PluginPermission | None = None
    detail: str | None = None


Handler = Callable[[PluginOperationContext], Awaitable[T]]
Middleware = Callable[[PluginOperationContext, Handler[T]], Awaitable[T]]


def apply_middleware[T](handler: Handler[T], middlewares: list[Middleware[T]]) -> Handler[T]:
    """Wrap *handler* in every middleware, outermost first ("the chain")."""
    for middleware in reversed(middlewares):
        handler = _bind(middleware, handler)
    return handler


def _bind[T](middleware: Middleware[T], next_handler: Handler[T]) -> Handler[T]:
    async def wrapped(context: PluginOperationContext) -> T:
        return await middleware(context, next_handler)

    return wrapped


async def logging_middleware[T](context: PluginOperationContext, next_handler: Handler[T]) -> T:
    """Log the start and outcome of every plugin operation."""
    logger.info(
        "Starting plugin operation.",
        extra={"extra_fields": {"plugin_id": context.plugin_id, "operation": context.operation}},
    )
    try:
        result = await next_handler(context)
    except Exception:
        logger.exception("Plugin operation failed.")
        raise
    logger.info(
        "Finished plugin operation.",
        extra={"extra_fields": {"plugin_id": context.plugin_id, "operation": context.operation}},
    )
    return result


def build_permission_middleware[T](permissions: PermissionRegistry) -> Middleware[T]:
    """Build a middleware enforcing granted permissions.

    Covers "Permission Enforcement" and "RBAC Validation".
    """

    async def middleware(context: PluginOperationContext, next_handler: Handler[T]) -> T:
        if context.required_permission is not None:
            permissions.require_permission(context.plugin_id, context.required_permission)
        return await next_handler(context)

    return middleware


def build_sandbox_middleware[T](sandboxes: dict[str, PluginSandbox]) -> Middleware[T]:
    """Build a middleware enforcing each plugin's own sandbox execution timeout.

    Covers "Sandbox Isolation".
    """

    async def middleware(context: PluginOperationContext, next_handler: Handler[T]) -> T:
        sandbox = sandboxes.get(context.plugin_id)
        if sandbox is None:
            return await next_handler(context)
        return await sandbox.run(next_handler(context))

    return middleware


async def audit_middleware[T](context: PluginOperationContext, next_handler: Handler[T]) -> T:
    """Audit every operation's failure ("Audit Every Operation")."""
    try:
        return await next_handler(context)
    except Exception as exc:
        plugin_audit.audit_plugin_failure(context.plugin_id, error=str(exc))
        raise


def build_telemetry_middleware[T](tracer: Tracer) -> Middleware[T]:
    """Build a middleware wrapping every operation in a trace span ("Telemetry")."""

    async def middleware(context: PluginOperationContext, next_handler: Handler[T]) -> T:
        with trace_plugin_execution(tracer, context.plugin_id, operation=context.operation):
            return await next_handler(context)

    return middleware


async def metrics_collection_middleware[T](
    context: PluginOperationContext, next_handler: Handler[T]
) -> T:
    """Record every operation's duration and outcome to Prometheus ("Metrics")."""
    with plugin_metrics.measure_execution(context.plugin_id):
        return await next_handler(context)


__all__ = [
    "Handler",
    "Middleware",
    "PluginOperationContext",
    "apply_middleware",
    "audit_middleware",
    "build_permission_middleware",
    "build_sandbox_middleware",
    "build_telemetry_middleware",
    "logging_middleware",
    "metrics_collection_middleware",
]
