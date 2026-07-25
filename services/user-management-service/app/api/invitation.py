"""POST /users/invite, /users/invite/resend, /users/invite/accept."""

from __future__ import annotations

from fastapi import APIRouter, Request
from shared_core.logging.context import get_log_context

from app.api.deps import CurrentUserId, InvitationSvc
from app.schemas.invitation import (
    AcceptInvitationRequest,
    InvitationResponse,
    InviteRequest,
    RejectInvitationRequest,
    ResendInvitationRequest,
)
from app.schemas.response import ResponseMeta, SuccessResponse
from app.schemas.user import UserSummary

router = APIRouter(prefix="/users/invite", tags=["Invitations"])


def _meta() -> ResponseMeta:
    return ResponseMeta(request_id=get_log_context().request_id or "unknown")


def _invite_base_url(request: Request) -> str:
    return f"{request.base_url}users/invite/accept"


@router.post("", response_model=SuccessResponse[InvitationResponse], status_code=201)
async def invite_user(
    body: InviteRequest,
    request: Request,
    invitations: InvitationSvc,
    current_user_id: CurrentUserId,
) -> SuccessResponse[InvitationResponse]:
    """Invite a new user by email ("Invite User")."""
    record, _raw_token = await invitations.invite(
        body.email,
        invited_by=current_user_id,
        message=body.message,
        invite_base_url=_invite_base_url(request),
    )
    data = InvitationResponse(
        id=record.id,
        email=record.email,
        status=record.status,
        resend_count=record.resend_count,
        expires_at=record.expires_at,
        created_at=record.created_at,
    )
    return SuccessResponse(message="Invitation sent.", data=data, meta=_meta())


@router.post("/resend", response_model=SuccessResponse[dict[str, bool]])
async def resend_invitation(
    body: ResendInvitationRequest,
    request: Request,
    invitations: InvitationSvc,
    _caller: CurrentUserId,
) -> SuccessResponse[dict[str, bool]]:
    """Resend a pending invitation ("Resend Invitation")."""
    await invitations.resend(body.email, invite_base_url=_invite_base_url(request))
    return SuccessResponse(message="Invitation resent.", data={"success": True}, meta=_meta())


@router.post("/reject", response_model=SuccessResponse[dict[str, bool]])
async def reject_invitation(
    body: RejectInvitationRequest, invitations: InvitationSvc
) -> SuccessResponse[dict[str, bool]]:
    """Reject an invitation ("Reject Invitation").

    Unauthenticated by design, same as ``/accept`` -- the token is the
    only credential needed to decline an invitation addressed to you.
    """
    await invitations.reject(body.token)
    return SuccessResponse(message="Invitation rejected.", data={"success": True}, meta=_meta())


@router.post("/accept", response_model=SuccessResponse[UserSummary])
async def accept_invitation(
    body: AcceptInvitationRequest, invitations: InvitationSvc
) -> SuccessResponse[UserSummary]:
    """Accept an invitation, creating a new user ("Accept Invitation").

    Unauthenticated by design -- the invitation token itself is the
    credential proving the caller is entitled to create this account.
    """
    user = await invitations.accept(
        token=body.token, username=body.username, display_name=body.display_name
    )
    data = UserSummary(
        id=user.id,
        username=user.username,
        email=user.email,
        display_name=user.display_name,
        avatar=user.avatar,
        status=user.status,
        created_at=user.created_at,
    )
    return SuccessResponse(message="Invitation accepted.", data=data, meta=_meta())


__all__ = ["router"]
