"""``/roles`` and ``/roles/{id}/permissions``.

Per docs/032 REST list. Mutating endpoints require the caller be
granted ``settings:manage`` (docs/032's ``ResourceType`` list has no
dedicated "Roles"/"Permissions" resource of its own -- role/permission/
policy administration is platform configuration, the closest listed
fit) -- see :mod:`app.authorization.guard`.
"""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends
from shared_core.logging.context import get_log_context

from app.api.deps import CurrentUserId, RolePermissionSvc, RoleSvc
from app.authorization.guard import require_permission
from app.models.enums import PermissionAction, ResourceType
from app.models.role import Role
from app.schemas.response import ResponseMeta, SuccessResponse
from app.schemas.role import RoleCreateRequest, RoleResponse, RoleUpdateRequest
from app.schemas.role_permission import GrantPermissionRequest

router = APIRouter(prefix="/roles", tags=["Roles"])

_ManageRoles = Depends(require_permission(ResourceType.SETTINGS, PermissionAction.MANAGE))


def _meta() -> ResponseMeta:
    return ResponseMeta(request_id=get_log_context().request_id or "unknown")


def _to_response(role: Role) -> RoleResponse:
    return RoleResponse(
        id=role.id,
        name=role.name,
        code=role.code,
        description=role.description,
        role_type=role.role_type,
        status=role.status,
        parent_role_id=role.parent_role_id,
        is_system=role.is_system,
        priority=role.priority,
        organization_id=role.organization_id,
        project_id=role.project_id,
        metadata=role.metadata_,
        created_at=role.created_at,
        updated_at=role.updated_at,
    )


@router.get("", response_model=SuccessResponse[list[RoleResponse]])
async def list_roles(roles: RoleSvc, _caller: CurrentUserId) -> SuccessResponse[list[RoleResponse]]:
    """List every role ("Role Management")."""
    records = await roles.list_all()
    return SuccessResponse(
        message="Roles retrieved.", data=[_to_response(r) for r in records], meta=_meta()
    )


@router.get("/{role_id}", response_model=SuccessResponse[RoleResponse])
async def get_role(
    role_id: UUID, roles: RoleSvc, _caller: CurrentUserId
) -> SuccessResponse[RoleResponse]:
    """Return one role."""
    role = await roles.get_by_id(role_id)
    return SuccessResponse(message="Role retrieved.", data=_to_response(role), meta=_meta())


@router.post(
    "", response_model=SuccessResponse[RoleResponse], status_code=201, dependencies=[_ManageRoles]
)
async def create_role(body: RoleCreateRequest, roles: RoleSvc) -> SuccessResponse[RoleResponse]:
    """Create a new role ("Create")."""
    role = await roles.create(
        name=body.name,
        code=body.code,
        description=body.description,
        role_type=body.role_type,
        parent_role_id=body.parent_role_id,
        priority=body.priority,
        project_id=body.project_id,
        metadata=body.metadata,
    )
    return SuccessResponse(message="Role created.", data=_to_response(role), meta=_meta())


@router.put("/{role_id}", response_model=SuccessResponse[RoleResponse], dependencies=[_ManageRoles])
async def update_role(
    role_id: UUID, body: RoleUpdateRequest, roles: RoleSvc
) -> SuccessResponse[RoleResponse]:
    """Replace a role's mutable fields ("Update")."""
    role = await roles.update(
        role_id,
        name=body.name,
        description=body.description,
        status=body.status,
        parent_role_id=body.parent_role_id,
        priority=body.priority,
        metadata=body.metadata,
    )
    return SuccessResponse(message="Role updated.", data=_to_response(role), meta=_meta())


@router.delete(
    "/{role_id}", response_model=SuccessResponse[dict[str, bool]], dependencies=[_ManageRoles]
)
async def delete_role(role_id: UUID, roles: RoleSvc) -> SuccessResponse[dict[str, bool]]:
    """Delete a role ("Delete")."""
    await roles.delete(role_id)
    return SuccessResponse(message="Role deleted.", data={"success": True}, meta=_meta())


@router.post(
    "/{role_id}/permissions",
    response_model=SuccessResponse[dict[str, bool]],
    status_code=201,
    dependencies=[_ManageRoles],
)
async def grant_permission(
    role_id: UUID,
    body: GrantPermissionRequest,
    role_permissions: RolePermissionSvc,
    caller: CurrentUserId,
) -> SuccessResponse[dict[str, bool]]:
    """Grant a permission to a role ("Assign")."""
    await role_permissions.grant(role_id, body.permission_id, granted_by=caller)
    return SuccessResponse(message="Permission granted.", data={"success": True}, meta=_meta())


@router.delete(
    "/{role_id}/permissions/{permission_id}",
    response_model=SuccessResponse[dict[str, bool]],
    dependencies=[_ManageRoles],
)
async def revoke_permission(
    role_id: UUID, permission_id: UUID, role_permissions: RolePermissionSvc
) -> SuccessResponse[dict[str, bool]]:
    """Revoke a permission from a role."""
    await role_permissions.revoke(role_id, permission_id)
    return SuccessResponse(message="Permission revoked.", data={"success": True}, meta=_meta())


__all__ = ["router"]
