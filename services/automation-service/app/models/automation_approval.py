"""``automation_approvals`` table. Per docs/040 "APPROVALS" "Support":
Single Approval, Multi-Level Approval, Conditional Approval,
Role-Based Approval, Approval Expiration, Approval History, Emergency
Override.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from shared_core.database.base import BaseModel
from sqlalchemy import DateTime, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.models.enums import ApprovalStatus, ApprovalType


class AutomationApproval(BaseModel):
    """One approval-workflow gate against a pending automation execution."""

    __tablename__ = "automation_approvals"

    execution_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("automation_executions.id", ondelete="CASCADE"), nullable=False, index=True
    )
    approval_type: Mapped[ApprovalType] = mapped_column(String(24), index=True)
    status: Mapped[ApprovalStatus] = mapped_column(
        String(16), default=ApprovalStatus.PENDING, index=True
    )
    level: Mapped[int] = mapped_column(Integer, default=1)
    requested_by: Mapped[uuid.UUID | None] = mapped_column(default=None)
    approver_id: Mapped[uuid.UUID | None] = mapped_column(default=None)
    comments: Mapped[str | None] = mapped_column(String(2048), default=None)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)


__all__ = ["AutomationApproval"]
