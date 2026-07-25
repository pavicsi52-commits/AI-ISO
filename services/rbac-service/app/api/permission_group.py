"""``/permission-groups``. Per docs/032 REST list."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from shared_core.logging.context import get_log_context

from app.api.deps import CurrentUserId, PermissionGroupSvc
from app.authorization.guard import require_permission
from app.models.enums import PermissionAction, ResourceType
from app.models.permission_group import PermissionGroup
from app.schemas.permission_group import PermissionGroupCreateRequest, PermissionGroupResponse
from app.schemas.response import ResponseMeta, SuccessResponse

router = APIRouter(prefix="/permission-groups", tags=["Permission Groups"])

_ManageGroups = Depends(require_permission(ResourceType.SETTINGS, PermissionAction.MANAGE))


def _meta() -> ResponseMeta:
    return ResponseMeta(request_id=get_log_context().request_id or "unknown")


def _to_response(group: PermissionGroup) -> PermissionGroupResponse:
    return PermissionGroupResponse(
        id=group.id,
        name=group.name,
        code=group.code,
        description=group.description,
        category=group.category,
        metadata=group.metadata_,
        created_at=group.created_at,
        updated_at=group.updated_at,
    )


@router.get("", response_model=SuccessResponse[list[PermissionGroupResponse]])
async def list_permission_groups(
    groups: PermissionGroupSvc, _caller: CurrentUserId
) -> SuccessResponse[list[PermissionGroupResponse]]:
    """List every permission group ("Permission Groups")."""
    records = await groups.list_all()
    return SuccessResponse(
        message="Permission groups retrieved.",
        data=[_to_response(g) for g in records],
        meta=_meta(),
    )


@router.post(
    "",
    response_model=SuccessResponse[PermissionGroupResponse],
    status_code=201,
    dependencies=[_ManageGroups],
)
async def create_permission_group(
    body: PermissionGroupCreateRequest, groups: PermissionGroupSvc
) -> SuccessResponse[PermissionGroupResponse]:
    """Create a new permission group ("Custom Groups")."""
    group = await groups.create(
        name=body.name,
        code=body.code,
        description=body.description,
        category=body.category,
        metadata=body.metadata,
    )
    return SuccessResponse(
        message="Permission group created.", data=_to_response(group), meta=_meta()
    )


__all__ = ["router"]
