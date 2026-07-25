"""Request/response schemas for the configuration approval workflow."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field

from app.models.enums import ApprovalStatus


class ConfigurationApprovalCreateRequest(BaseModel):
    """Body of ``POST /configurations/approvals`` -- request an approval."""

    profile_id: UUID | None = None
    version_id: UUID | None = None
    rollback_id: UUID | None = None
    level: int = Field(default=1, ge=1)
    requested_by: UUID | None = None


class ConfigurationApprovalDecisionRequest(BaseModel):
    """Body of ``PATCH /configurations/approvals/{id}`` -- approve/reject."""

    status: ApprovalStatus
    approver_id: UUID | None = None
    comments: str | None = Field(default=None, max_length=2048)


class ConfigurationApprovalResponse(BaseModel):
    """One approval-workflow step against a profile, version, or rollback."""

    id: UUID
    profile_id: UUID | None
    version_id: UUID | None
    rollback_id: UUID | None
    status: ApprovalStatus
    level: int
    requested_by: UUID | None
    approver_id: UUID | None
    comments: str | None
    decided_at: datetime | None


__all__ = [
    "ConfigurationApprovalCreateRequest",
    "ConfigurationApprovalDecisionRequest",
    "ConfigurationApprovalResponse",
]
