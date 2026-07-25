"""``/permissions``. Per docs/032 REST list."""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends
from shared_core.logging.context import get_log_context

from app.api.deps import CurrentUserId, PermissionSvc
from app.authorization.guard import require_permission
from app.models.enums import PermissionAction, ResourceType
from app.models.permission import Permission
from app.schemas.permission import (
    PermissionCreateRequest,
    PermissionResponse,
    PermissionUpdateRequest,
)
from app.schemas.response import ResponseMeta, SuccessResponse

router = APIRouter(prefix="/permissions", tags=["Permissions"])

_ManagePermissions = Depends(require_permission(ResourceType.SETTINGS, PermissionAction.MANAGE))


def _meta() -> ResponseMeta:
    return ResponseMeta(request_id=get_log_context().request_id or "unknown")


def _to_response(permission: Permission) -> PermissionResponse:
    return PermissionResponse(
        id=permission.id,
        name=permission.name,
        code=permission.code,
        description=permission.description,
        category=permission.category,
        resource=permission.resource,
        action=permission.action,
        scope=permission.scope,
        status=permission.status,
        version=permission.version,
        permission_group_id=permission.permission_group_id,
        metadata=permission.metadata_,
        created_at=permission.created_at,
        updated_at=permission.updated_at,
    )


@router.get("", response_model=SuccessResponse[list[PermissionResponse]])
async def list_permissions(
    permissions: PermissionSvc, _caller: CurrentUserId
) -> SuccessResponse[list[PermissionResponse]]:
    """List every permission ("Permission Management")."""
    records = await permissions.list_all()
    return SuccessResponse(
        message="Permissions retrieved.", data=[_to_response(p) for p in records], meta=_meta()
    )


@router.post(
    "",
    response_model=SuccessResponse[PermissionResponse],
    status_code=201,
    dependencies=[_ManagePermissions],
)
async def create_permission(
    body: PermissionCreateRequest, permissions: PermissionSvc
) -> SuccessResponse[PermissionResponse]:
    """Create a new permission ("Create")."""
    permission = await permissions.create(
        name=body.name,
        code=body.code,
        description=body.description,
        category=body.category,
        resource=body.resource,
        action=body.action,
        scope=body.scope,
        permission_group_id=body.permission_group_id,
        metadata=body.metadata,
    )
    return SuccessResponse(
        message="Permission created.", data=_to_response(permission), meta=_meta()
    )


@router.put(
    "/{permission_id}",
    response_model=SuccessResponse[PermissionResponse],
    dependencies=[_ManagePermissions],
)
async def update_permission(
    permission_id: UUID, body: PermissionUpdateRequest, permissions: PermissionSvc
) -> SuccessResponse[PermissionResponse]:
    """Update a permission's mutable fields ("Update")."""
    permission = await permissions.update(
        permission_id,
        name=body.name,
        description=body.description,
        category=body.category,
        status=body.status,
        permission_group_id=body.permission_group_id,
        metadata=body.metadata,
    )
    return SuccessResponse(
        message="Permission updated.", data=_to_response(permission), meta=_meta()
    )


@router.delete(
    "/{permission_id}",
    response_model=SuccessResponse[dict[str, bool]],
    dependencies=[_ManagePermissions],
)
async def delete_permission(
    permission_id: UUID, permissions: PermissionSvc
) -> SuccessResponse[dict[str, bool]]:
    """Delete a permission ("Delete")."""
    await permissions.delete(permission_id)
    return SuccessResponse(message="Permission deleted.", data={"success": True}, meta=_meta())


__all__ = ["router"]
