"""Execution middleware.

Per docs/028_Enterprise_Workflow_SDK.md.txt "SECURITY": RBAC, Tenant
Isolation, Secret Handling, Permission Validation, Secure Variables,
Audit Privileged Workflows. Secret Handling/Secure Variables are
already enforced by :class:`shared_core.workflow.variables.VariableStore`
(``VariableScope.SECRET`` masking) and are not duplicated here; this
module supplies the remaining cross-cutting concerns as a middleware
chain wrapping a single workflow-level operation -- the same
``apply_middleware``/``_bind`` chain shape as
:mod:`shared_core.connectors.middleware`, parameterized so it can wrap
:meth:`shared_core.workflow.engine.WorkflowEngine.run` or any other
workflow-level operation identically.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import TypeVar

from shared_core.exceptions.authorization import AuthorizationError
from shared_core.logging.logger import get_logger
from shared_core.workflow import audit as workflow_audit

logger = get_logger("shared_core.workflow")

T = TypeVar("T")


@dataclass(frozen=True, slots=True)
class WorkflowOperationContext:
    """Identifies one workflow-level operation a middleware chain wraps."""

    workflow_id: str
    execution_id: str
    operation: str
    organization_id: str | None = None
    user_id: str | None = None
    privileged: bool = False


Handler = Callable[[WorkflowOperationContext], Awaitable[T]]
Middleware = Callable[[WorkflowOperationContext, Handler[T]], Awaitable[T]]
PermissionChecker = Callable[[WorkflowOperationContext], Awaitable[bool]]


def apply_middleware[T](handler: Handler[T], middlewares: list[Middleware[T]]) -> Handler[T]:
    """Wrap *handler* in every middleware, outermost first ("the chain")."""
    for middleware in reversed(middlewares):
        handler = _bind(middleware, handler)
    return handler


def _bind[T](middleware: Middleware[T], next_handler: Handler[T]) -> Handler[T]:
    async def wrapped(context: WorkflowOperationContext) -> T:
        return await middleware(context, next_handler)

    return wrapped


async def logging_middleware[T](context: WorkflowOperationContext, next_handler: Handler[T]) -> T:
    """Log the start and outcome of every workflow operation."""
    logger.info(
        "Starting workflow operation.",
        extra={
            "extra_fields": {
                "workflow_id": context.workflow_id,
                "operation": context.operation,
            }
        },
    )
    try:
        result = await next_handler(context)
    except Exception:
        logger.exception("Workflow operation failed.")
        raise
    logger.info(
        "Finished workflow operation.",
        extra={
            "extra_fields": {
                "workflow_id": context.workflow_id,
                "operation": context.operation,
            }
        },
    )
    return result


def build_rbac_middleware[T](checker: PermissionChecker) -> Middleware[T]:
    """Build a middleware denying an operation unless *checker* approves.

    Covers "RBAC" and "Permission Validation".
    """

    async def middleware(context: WorkflowOperationContext, next_handler: Handler[T]) -> T:
        if not await checker(context):
            raise AuthorizationError(
                f"Operation {context.operation!r} denied for workflow {context.workflow_id!r}."
            )
        return await next_handler(context)

    return middleware


def build_tenant_isolation_middleware[T](expected_organization_id: str) -> Middleware[T]:
    """Build a middleware denying cross-tenant access ("Tenant Isolation")."""

    async def middleware(context: WorkflowOperationContext, next_handler: Handler[T]) -> T:
        mismatched = (
            context.organization_id is not None
            and context.organization_id != expected_organization_id
        )
        if mismatched:
            raise AuthorizationError(
                f"Workflow {context.workflow_id!r} does not belong to organization "
                f"{expected_organization_id!r}."
            )
        return await next_handler(context)

    return middleware


async def audit_privileged_middleware[T](
    context: WorkflowOperationContext, next_handler: Handler[T]
) -> T:
    """Audit access to privileged workflow operations ("Audit Privileged Workflows")."""
    if context.privileged:
        workflow_audit.audit_privileged_access(
            context.execution_id,
            context.workflow_id,
            operation=context.operation,
            actor_id=context.user_id,
        )
    return await next_handler(context)


__all__ = [
    "Handler",
    "Middleware",
    "PermissionChecker",
    "WorkflowOperationContext",
    "apply_middleware",
    "audit_privileged_middleware",
    "build_rbac_middleware",
    "build_tenant_isolation_middleware",
    "logging_middleware",
]
