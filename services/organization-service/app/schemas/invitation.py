"""Request/response schemas for ``/organizations/{id}/invite`` and
``/organizations/invite/{accept,reject}``.
"""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, EmailStr, Field

from app.models.enums import InvitationStatus, MemberRole


class InviteMemberRequest(BaseModel):
    """Body of ``POST /organizations/{id}/invite``."""

    email: EmailStr
    role: MemberRole = MemberRole.MEMBER
    department_id: UUID | None = None
    team_id: UUID | None = None
    message: str | None = Field(default=None, max_length=2048)


class AcceptInvitationRequest(BaseModel):
    """Body of ``POST /organizations/invite/accept`` -- unauthenticated: the
    token itself is the credential, the same design
    ``services/user-management-service``'s own invitation flow established.
    """

    token: str
    user_id: UUID


class RejectInvitationRequest(BaseModel):
    """Body of ``POST /organizations/invite/reject``."""

    token: str


class InvitationResponse(BaseModel):
    """One invitation, in full (never includes the raw token)."""

    id: UUID
    organization_id: UUID
    email: str
    invited_by: UUID
    role: MemberRole
    department_id: UUID | None
    team_id: UUID | None
    status: InvitationStatus
    resend_count: int
    expires_at: datetime
    accepted_at: datetime | None
    rejected_at: datetime | None
    created_at: datetime


__all__ = [
    "AcceptInvitationRequest",
    "InvitationResponse",
    "InviteMemberRequest",
    "RejectInvitationRequest",
]
