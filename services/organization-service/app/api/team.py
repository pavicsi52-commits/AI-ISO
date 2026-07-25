"""``/organizations/{id}/teams`` and ``/teams/{id}``. Per docs/033 REST list.

See ``app/api/department.py``'s docstring for why this file has two
router prefixes and why ``/teams/{id}`` checks admin membership
manually rather than via ``Depends()``.
"""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends
from shared_core.logging.context import get_log_context

from app.api.deps import (
    CurrentUserId,
    MemberSvc,
    TeamSvc,
    require_admin,
    require_member,
    require_role_in_org,
)
from app.models.enums import MemberRole
from app.models.team import Team
from app.schemas.response import ResponseMeta, SuccessResponse
from app.schemas.team import TeamCreateRequest, TeamResponse, TeamUpdateRequest

org_router = APIRouter(prefix="/organizations/{organization_id}/teams", tags=["Teams"])
router = APIRouter(prefix="/teams", tags=["Teams"])


def _meta() -> ResponseMeta:
    return ResponseMeta(request_id=get_log_context().request_id or "unknown")


def _to_response(team: Team) -> TeamResponse:
    return TeamResponse(
        id=team.id,
        organization_id=team.organization_id,
        name=team.name,
        code=team.code,
        description=team.description,
        department_id=team.department_id,
        business_unit_id=team.business_unit_id,
        team_lead_id=team.team_lead_id,
        metadata=team.metadata_,
        created_at=team.created_at,
        updated_at=team.updated_at,
    )


@org_router.get(
    "", response_model=SuccessResponse[list[TeamResponse]], dependencies=[Depends(require_member)]
)
async def list_teams(
    organization_id: UUID, teams: TeamSvc, _caller: CurrentUserId
) -> SuccessResponse[list[TeamResponse]]:
    """List every team in an organization ("Team Management")."""
    records = await teams.list_for_org(organization_id)
    return SuccessResponse(
        message="Teams retrieved.", data=[_to_response(t) for t in records], meta=_meta()
    )


@org_router.post(
    "",
    response_model=SuccessResponse[TeamResponse],
    status_code=201,
    dependencies=[Depends(require_admin)],
)
async def create_team(
    organization_id: UUID, body: TeamCreateRequest, teams: TeamSvc
) -> SuccessResponse[TeamResponse]:
    """Create a new team ("Create")."""
    team = await teams.create(
        organization_id,
        name=body.name,
        code=body.code,
        description=body.description,
        department_id=body.department_id,
        business_unit_id=body.business_unit_id,
        team_lead_id=body.team_lead_id,
        metadata=body.metadata,
    )
    return SuccessResponse(message="Team created.", data=_to_response(team), meta=_meta())


@router.put("/{team_id}", response_model=SuccessResponse[TeamResponse])
async def update_team(
    team_id: UUID,
    body: TeamUpdateRequest,
    teams: TeamSvc,
    caller: CurrentUserId,
    members: MemberSvc,
) -> SuccessResponse[TeamResponse]:
    """Update a team's mutable fields ("Update")."""
    existing = await teams.get_by_id(team_id)
    await require_role_in_org(existing.organization_id, caller, members, MemberRole.ADMIN)
    team = await teams.update(
        team_id,
        name=body.name,
        description=body.description,
        department_id=body.department_id,
        business_unit_id=body.business_unit_id,
        team_lead_id=body.team_lead_id,
        metadata=body.metadata,
    )
    return SuccessResponse(message="Team updated.", data=_to_response(team), meta=_meta())


@router.delete("/{team_id}", response_model=SuccessResponse[dict[str, bool]])
async def delete_team(
    team_id: UUID, teams: TeamSvc, caller: CurrentUserId, members: MemberSvc
) -> SuccessResponse[dict[str, bool]]:
    """Delete a team ("Delete")."""
    existing = await teams.get_by_id(team_id)
    await require_role_in_org(existing.organization_id, caller, members, MemberRole.ADMIN)
    await teams.delete(team_id)
    return SuccessResponse(message="Team deleted.", data={"success": True}, meta=_meta())


__all__ = ["org_router", "router"]
