"""``/users/{id}/roles`` and ``/users/{id}/permissions``.

Per docs/032 REST list. Guarded with ``users:assign``/``users:read``
(assigning a role is an action *on a user*) rather than the
``settings:manage`` this package's other admin routers use -- see
:mod:`app.authorization.guard`.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from shared_core.logging.context import get_log_context

from app.api.deps import CurrentUserId, EvaluatorSvc, RoleAssignmentSvc
from app.authorization.guard import require_permission
from app.models.enums import PermissionAction, ResourceType, SubjectType
from app.schemas.response import ResponseMeta, SuccessResponse
from app.schemas.role_assignment import (
    AssignRoleRequest,
    RoleAssignmentResponse,
    UserPermissionsResponse,
)
from app.services.role_assignment import Assignment

router = APIRouter(prefix="/users/{user_id}", tags=["Role Assignment"])

_AssignRoles = Depends(require_permission(ResourceType.USERS, PermissionAction.ASSIGN))
_ReadUserPermissions = Depends(require_permission(ResourceType.USERS, PermissionAction.READ))


def _meta() -> ResponseMeta:
    return ResponseMeta(request_id=get_log_context().request_id or "unknown")


def _to_response(assignment: Assignment) -> RoleAssignmentResponse:
    return RoleAssignmentResponse(
        id=assignment.id,
        user_id=assignment.user_id,
        role_id=assignment.role_id,
        scope_type=assignment.scope_type,
        scope_id=assignment.scope_id,
        status=assignment.status,
        assigned_by=assignment.assigned_by,
        expires_at=assignment.expires_at,
        created_at=assignment.created_at,
    )


@router.post(
    "/roles",
    response_model=SuccessResponse[RoleAssignmentResponse],
    status_code=201,
    dependencies=[_AssignRoles],
)
async def assign_role(
    user_id: UUID, body: AssignRoleRequest, assignments: RoleAssignmentSvc, caller: CurrentUserId
) -> SuccessResponse[RoleAssignmentResponse]:
    """Assign a role to *user_id* ("Role Assignment")."""
    assignment = await assignments.assign(
        user_id,
        body.role_id,
        scope_type=body.scope_type,
        scope_id=body.scope_id,
        expires_at=body.expires_at,
        assigned_by=caller,
    )
    return SuccessResponse(message="Role assigned.", data=_to_response(assignment), meta=_meta())


@router.delete(
    "/roles/{role_id}",
    response_model=SuccessResponse[dict[str, bool]],
    dependencies=[_AssignRoles],
)
async def remove_role(
    user_id: UUID,
    role_id: UUID,
    assignments: RoleAssignmentSvc,
    scope_type: Annotated[SubjectType, Query()] = SubjectType.GLOBAL,
    scope_id: Annotated[UUID | None, Query()] = None,
) -> SuccessResponse[dict[str, bool]]:
    """Remove a role assignment from *user_id*."""
    await assignments.remove(user_id, role_id, scope_type=scope_type, scope_id=scope_id)
    return SuccessResponse(message="Role removed.", data={"success": True}, meta=_meta())


@router.get(
    "/permissions",
    response_model=SuccessResponse[UserPermissionsResponse],
    dependencies=[_ReadUserPermissions],
)
async def get_user_permissions(
    user_id: UUID,
    evaluator: EvaluatorSvc,
    organization_id: Annotated[UUID | None, Query()] = None,
    project_id: Annotated[UUID | None, Query()] = None,
) -> SuccessResponse[UserPermissionsResponse]:
    """Return *user_id*'s aggregated effective permissions ("Permission Aggregation")."""
    permissions, role_codes = await evaluator.effective_permission_codes(
        user_id, organization_id=organization_id, project_id=project_id
    )
    data = UserPermissionsResponse(
        user_id=user_id,
        organization_id=organization_id,
        project_id=project_id,
        permissions=permissions,
        role_codes=role_codes,
        computed_at=datetime.now(UTC),
    )
    return SuccessResponse(message="Permissions retrieved.", data=data, meta=_meta())


__all__ = ["router"]
