"""``playbook_approvals`` table. Per docs/041 "APPROVALS" "Support":
Technical Approval, Security Approval, Operational Approval, Publishing
Approval, Approval History, Comments, Revisions.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from shared_core.database.base import BaseModel
from sqlalchemy import DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.enums import ApprovalStatus, ApprovalType


class PlaybookApproval(BaseModel):
    """One approval-workflow gate against a playbook (or one of its versions)."""

    __tablename__ = "playbook_approvals"

    playbook_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("playbooks.id", ondelete="CASCADE"), nullable=False, index=True
    )
    version_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("playbook_versions.id", ondelete="CASCADE"), default=None, index=True
    )
    approval_type: Mapped[ApprovalType] = mapped_column(String(24), index=True)
    status: Mapped[ApprovalStatus] = mapped_column(
        String(16), default=ApprovalStatus.PENDING, index=True
    )
    level: Mapped[int] = mapped_column(Integer, default=1)
    requested_by: Mapped[uuid.UUID | None] = mapped_column(default=None)
    approver_id: Mapped[uuid.UUID | None] = mapped_column(default=None)
    comments: Mapped[str | None] = mapped_column(Text, default=None)
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)


__all__ = ["PlaybookApproval"]
