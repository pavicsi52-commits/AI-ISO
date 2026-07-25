"""Request/response schemas for the automation execution approval workflow."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field

from app.models.enums import ApprovalStatus, ApprovalType


class AutomationApprovalCreateRequest(BaseModel):
    """Body of ``POST /automation/executions/{id}/approvals``."""

    approval_type: ApprovalType = ApprovalType.SINGLE
    level: int = Field(default=1, ge=1)
    requested_by: UUID | None = None
    expires_at: datetime | None = None


class AutomationApprovalDecisionRequest(BaseModel):
    """Body of ``PATCH /automation/approvals/{id}`` -- approve/reject."""

    status: ApprovalStatus
    approver_id: UUID | None = None
    comments: str | None = Field(default=None, max_length=2048)


class AutomationApprovalResponse(BaseModel):
    """One approval-workflow gate against a pending automation execution."""

    id: UUID
    execution_id: UUID
    approval_type: ApprovalType
    status: ApprovalStatus
    level: int
    requested_by: UUID | None
    approver_id: UUID | None
    comments: str | None
    expires_at: datetime | None
    decided_at: datetime | None


__all__ = [
    "AutomationApprovalCreateRequest",
    "AutomationApprovalDecisionRequest",
    "AutomationApprovalResponse",
]
