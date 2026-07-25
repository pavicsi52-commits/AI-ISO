"""``/inventory/groups``. Per docs/036 REST list and "GROUPS": Static,
Dynamic, Rule-Based, Location, Application, Environment, Custom Groups.
"""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter
from shared_core.logging.context import get_log_context

from app.api.asset import asset_to_response
from app.api.deps import CurrentUserId, GroupSvc, TagSvc
from app.models.asset_group import AssetGroup
from app.schemas.asset import AssetResponse
from app.schemas.group import AssetGroupCreateRequest, AssetGroupResponse
from app.schemas.response import ResponseMeta, SuccessResponse

router = APIRouter(prefix="/inventory/groups", tags=["Groups"])


def _meta() -> ResponseMeta:
    return ResponseMeta(request_id=get_log_context().request_id or "unknown")


def _to_response(group: AssetGroup) -> AssetGroupResponse:
    return AssetGroupResponse(
        id=group.id,
        organization_id=group.organization_id,
        name=group.name,
        description=group.description,
        group_type=group.group_type,
        rule=group.rule,
        member_asset_ids=group.member_asset_ids,
    )


@router.get("", response_model=SuccessResponse[list[AssetGroupResponse]])
async def list_groups(
    organization_id: UUID, groups: GroupSvc, _caller: CurrentUserId
) -> SuccessResponse[list[AssetGroupResponse]]:
    """List every group defined for *organization_id* ("Asset Groups")."""
    records = await groups.list_for_org(organization_id)
    return SuccessResponse(
        message="Groups retrieved.", data=[_to_response(record) for record in records], meta=_meta()
    )


@router.post("", response_model=SuccessResponse[AssetGroupResponse], status_code=201)
async def create_group(
    body: AssetGroupCreateRequest, groups: GroupSvc, _caller: CurrentUserId
) -> SuccessResponse[AssetGroupResponse]:
    """Create a new group.

    Raises:
        ConflictError: If *name* is already taken within *organization_id*.
    """
    group = await groups.create(
        organization_id=body.organization_id,
        name=body.name,
        description=body.description,
        group_type=body.group_type,
        rule=body.rule,
        member_asset_ids=body.member_asset_ids,
    )
    return SuccessResponse(message="Group created.", data=_to_response(group), meta=_meta())


@router.get("/{group_id}/members", response_model=SuccessResponse[list[AssetResponse]])
async def get_group_members(
    group_id: UUID, groups: GroupSvc, tags: TagSvc, _caller: CurrentUserId
) -> SuccessResponse[list[AssetResponse]]:
    """Resolve *group_id*'s current membership -- live for dynamic/
    rule-based groups, stored for every other group type.

    Raises:
        NotFoundError: If no such group exists.
    """
    members = await groups.resolve_members(group_id)
    data = [await asset_to_response(asset, tags) for asset in members]
    return SuccessResponse(message="Group members retrieved.", data=data, meta=_meta())


__all__ = ["router"]
