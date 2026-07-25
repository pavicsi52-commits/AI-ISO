"""Protects this service's own admin endpoints with itself.

A FastAPI dependency factory: ``Depends(require_permission(resource,
action))`` runs the exact same
:class:`~app.evaluators.authorization_evaluator.AuthorizationEvaluator`
that answers ``POST /authorization/evaluate`` against the *caller's*
own identity, denying the request with
:class:`~shared_core.exceptions.authorization.AuthorizationError` (403)
if it wouldn't itself be granted. This is how the RBAC service enforces
"least privilege" (docs/032 "SECURITY") on its own role/permission/
policy-management surface, without a second, parallel authorization
mechanism.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable

from shared_core.exceptions.authorization import AuthorizationError

from app.api.deps import CurrentUserId, EvaluatorSvc
from app.models.enums import AuthorizationDecision, PermissionAction, ResourceType


def require_permission(
    resource: ResourceType, action: PermissionAction
) -> Callable[[CurrentUserId, EvaluatorSvc], Awaitable[None]]:
    """Build a dependency requiring the caller be granted *action* on *resource*."""

    async def _guard(user_id: CurrentUserId, evaluator: EvaluatorSvc) -> None:
        result = await evaluator.evaluate(
            user_id=user_id,
            action=action,
            resource_type=resource,
            resource_id=None,
            organization_id=None,
            project_id=None,
            context={},
        )
        if result.decision != AuthorizationDecision.ALLOW:
            raise AuthorizationError(
                f"You do not have permission to {action.value} {resource.value}."
            )

    return _guard


__all__ = ["require_permission"]
