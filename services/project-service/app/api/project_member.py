"""``/projects/{id}/members``. Per docs/034 REST list."""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends
from shared_core.logging.context import get_log_context

from app.api.deps import (
    CurrentUserId,
    MemberSvc,
    ProjSvc,
    RoleSvc,
    require_project_admin,
    require_project_member,
)
from app.models.project_member import ProjectMember
from app.models.project_role import OWNER_ROLE_ID
from app.schemas.project_member import (
    AddMemberRequest,
    ProjectMemberResponse,
    UpdateMemberRoleRequest,
)
from app.schemas.response import ResponseMeta, SuccessResponse

router = APIRouter(prefix="/projects/{project_id}/members", tags=["Project Members"])


def _meta() -> ResponseMeta:
    return ResponseMeta(request_id=get_log_context().request_id or "unknown")


async def _to_response(member: ProjectMember, roles: RoleSvc) -> ProjectMemberResponse:
    role = await roles.get_by_id(member.role_id)
    return ProjectMemberResponse(
        id=member.id,
        project_id=member.project_id,
        user_id=member.user_id,
        role_id=member.role_id,
        role_code=role.code,
        role_name=role.name,
        status=member.status,
        invited_by=member.invited_by,
        created_at=member.created_at,
    )


@router.get(
    "",
    response_model=SuccessResponse[list[ProjectMemberResponse]],
    dependencies=[Depends(require_project_member)],
)
async def list_members(
    project_id: UUID, members: MemberSvc, roles: RoleSvc
) -> SuccessResponse[list[ProjectMemberResponse]]:
    """List every member of a project ("Track Membership History")."""
    records = await members.list_for_project(project_id)
    data = [await _to_response(m, roles) for m in records]
    return SuccessResponse(message="Members retrieved.", data=data, meta=_meta())


@router.post(
    "",
    response_model=SuccessResponse[ProjectMemberResponse],
    status_code=201,
    dependencies=[Depends(require_project_admin)],
)
async def add_member(
    project_id: UUID,
    body: AddMemberRequest,
    projects: ProjSvc,
    members: MemberSvc,
    roles: RoleSvc,
    caller: CurrentUserId,
) -> SuccessResponse[ProjectMemberResponse]:
    """Add a member to a project ("Invite Member")."""
    project = await projects.get_by_id(project_id)
    role = await roles.get_by_code(project_id, body.role_code)
    member = await members.add(
        project_id,
        body.user_id,
        organization_id=project.organization_id,
        role_id=role.id,
        invited_by=caller,
    )
    return SuccessResponse(
        message="Member added.", data=await _to_response(member, roles), meta=_meta()
    )


@router.delete(
    "/{member_user_id}",
    response_model=SuccessResponse[dict[str, bool]],
    dependencies=[Depends(require_project_admin)],
)
async def remove_member(
    project_id: UUID, member_user_id: UUID, projects: ProjSvc, members: MemberSvc
) -> SuccessResponse[dict[str, bool]]:
    """Remove a member from a project ("Remove Member")."""
    project = await projects.get_by_id(project_id)
    await members.remove(project_id, member_user_id, organization_id=project.organization_id)
    return SuccessResponse(message="Member removed.", data={"success": True}, meta=_meta())


@router.put(
    "/{member_user_id}/roles",
    response_model=SuccessResponse[ProjectMemberResponse],
    dependencies=[Depends(require_project_admin)],
)
async def update_member_role(
    project_id: UUID,
    member_user_id: UUID,
    body: UpdateMemberRoleRequest,
    projects: ProjSvc,
    members: MemberSvc,
    roles: RoleSvc,
) -> SuccessResponse[ProjectMemberResponse]:
    """Change a member's role ("Assign Roles").

    Assigning the Owner role instead performs a full ownership transfer
    ("Transfer Ownership"): the project's authoritative ``owner_id``
    field changes, the new owner's membership is promoted to Owner, and
    the previous owner (``project.owner_id`` before this call) is
    demoted to Administrator.
    """
    project = await projects.get_by_id(project_id)
    role = await roles.get_by_code(project_id, body.role_code)
    if role.id == OWNER_ROLE_ID:
        member = await members.transfer_ownership(
            project_id,
            current_owner_id=project.owner_id,
            new_owner_id=member_user_id,
            organization_id=project.organization_id,
        )
        await projects.set_owner(project_id, new_owner_id=member_user_id)
    else:
        member = await members.update_role(
            project_id, member_user_id, role_id=role.id, organization_id=project.organization_id
        )
    return SuccessResponse(
        message="Member role updated.", data=await _to_response(member, roles), meta=_meta()
    )


__all__ = ["router"]
