"""``POST /organizations/{id}/invite`` and ``/organizations/invite/{accept,reject}``.

``POST /organizations/{id}/invite`` is explicit in docs/033's own REST
list; ``accept``/``reject`` are the necessary, unauthenticated
counterparts docs/033's "ORGANIZATION INVITATIONS" functional section
requires ("Support ... Accept, Reject") but the REST list itself
doesn't separately enumerate -- the same design already established for
``services/user-management-service``'s own invitation flow, whose
accept/reject endpoints are unauthenticated by design (the token itself
is the credential).
"""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, Request
from shared_core.logging.context import get_log_context

from app.api.deps import CurrentUserId, InvitationSvc, require_admin
from app.models.invitation import OrganizationInvitation
from app.schemas.invitation import (
    AcceptInvitationRequest,
    InvitationResponse,
    InviteMemberRequest,
    RejectInvitationRequest,
)
from app.schemas.response import ResponseMeta, SuccessResponse

org_router = APIRouter(prefix="/organizations/{organization_id}/invite", tags=["Invitations"])
router = APIRouter(prefix="/organizations/invite", tags=["Invitations"])


def _meta() -> ResponseMeta:
    return ResponseMeta(request_id=get_log_context().request_id or "unknown")


def _to_response(invitation: OrganizationInvitation) -> InvitationResponse:
    return InvitationResponse(
        id=invitation.id,
        organization_id=invitation.organization_id,
        email=invitation.email,
        invited_by=invitation.invited_by,
        role=invitation.role,
        department_id=invitation.department_id,
        team_id=invitation.team_id,
        status=invitation.status,
        resend_count=invitation.resend_count,
        expires_at=invitation.expires_at,
        accepted_at=invitation.accepted_at,
        rejected_at=invitation.rejected_at,
        created_at=invitation.created_at,
    )


@org_router.post(
    "",
    response_model=SuccessResponse[InvitationResponse],
    status_code=201,
    dependencies=[Depends(require_admin)],
)
async def invite_member(
    organization_id: UUID,
    body: InviteMemberRequest,
    invitations: InvitationSvc,
    caller: CurrentUserId,
    request: Request,
) -> SuccessResponse[InvitationResponse]:
    """Invite a member to an organization ("Invite Member")."""
    record, _raw_token = await invitations.invite(
        organization_id,
        email=body.email,
        invited_by=caller,
        role=body.role,
        department_id=body.department_id,
        team_id=body.team_id,
        message=body.message,
        invite_base_url=str(request.base_url) + "organizations/invite/accept",
    )
    return SuccessResponse(message="Invitation sent.", data=_to_response(record), meta=_meta())


@router.post("/accept", response_model=SuccessResponse[dict[str, str]])
async def accept_invitation(
    body: AcceptInvitationRequest, invitations: InvitationSvc
) -> SuccessResponse[dict[str, str]]:
    """Accept an invitation, creating a new membership ("Accept")."""
    member = await invitations.accept(token=body.token, user_id=body.user_id)
    return SuccessResponse(
        message="Invitation accepted.",
        data={"organization_id": str(member.organization_id), "member_id": str(member.id)},
        meta=_meta(),
    )


@router.post("/reject", response_model=SuccessResponse[dict[str, bool]])
async def reject_invitation(
    body: RejectInvitationRequest, invitations: InvitationSvc
) -> SuccessResponse[dict[str, bool]]:
    """Reject an invitation ("Reject")."""
    await invitations.reject(body.token)
    return SuccessResponse(message="Invitation rejected.", data={"success": True}, meta=_meta())


__all__ = ["org_router", "router"]
