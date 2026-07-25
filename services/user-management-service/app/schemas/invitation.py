"""Request/response schemas for the invitation flow."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, EmailStr, Field

from app.models.enums import InvitationStatus


class InviteRequest(BaseModel):
    """Body of ``POST /users/invite``."""

    email: EmailStr
    message: str | None = Field(default=None, max_length=2048)


class BulkInviteRequest(BaseModel):
    """Body of a bulk invite (multiple emails, one message)."""

    emails: list[EmailStr] = Field(min_length=1, max_length=500)
    message: str | None = Field(default=None, max_length=2048)


class ResendInvitationRequest(BaseModel):
    """Body of ``POST /users/invite/resend``."""

    email: EmailStr


class AcceptInvitationRequest(BaseModel):
    """Body of ``POST /users/invite/accept``."""

    token: str
    username: str
    display_name: str | None = Field(default=None, max_length=255)


class RejectInvitationRequest(BaseModel):
    """Body of ``POST /users/invite/reject``."""

    token: str


class InvitationResponse(BaseModel):
    """One invitation's public-safe view."""

    id: UUID
    email: str
    status: InvitationStatus
    resend_count: int
    expires_at: datetime
    created_at: datetime


__all__ = [
    "AcceptInvitationRequest",
    "BulkInviteRequest",
    "InvitationResponse",
    "InviteRequest",
    "RejectInvitationRequest",
    "ResendInvitationRequest",
]
