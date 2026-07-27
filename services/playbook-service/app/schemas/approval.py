"""Request/response schemas for playbook approvals."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field

from app.models.enums import ApprovalStatus, ApprovalType


class PlaybookApprovalCreateRequest(BaseModel):
    """Body of ``POST /playbooks/{id}/approve`` -- requests and
    immediately records an approval decision in one call.
    """

    version_id: UUID | None = None
    approval_type: ApprovalType = ApprovalType.TECHNICAL
    level: int = Field(default=1, ge=1)
    requested_by: UUID | None = None
    comments: str | None = Field(default=None, max_length=4096)


class PlaybookApprovalDecisionRequest(BaseModel):
    """Body of the approval-decision action."""

    status: ApprovalStatus
    approver_id: UUID | None = None
    comments: str | None = Field(default=None, max_length=4096)


class PlaybookApprovalResponse(BaseModel):
    """One approval-workflow gate against a playbook (or one of its versions)."""

    id: UUID
    playbook_id: UUID
    version_id: UUID | None
    approval_type: ApprovalType
    status: ApprovalStatus
    level: int
    requested_by: UUID | None
    approver_id: UUID | None
    comments: str | None
    decided_at: datetime | None


__all__ = [
    "PlaybookApprovalCreateRequest",
    "PlaybookApprovalDecisionRequest",
    "PlaybookApprovalResponse",
]
