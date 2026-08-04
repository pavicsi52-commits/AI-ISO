"""``change_approvals`` -- the approval chain for one change.

One row per required approver, not one row per change: a multi-level or
role-based approval policy needs several people to weigh in
independently, and a chain is only as trustworthy as each link being its
own auditable record.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from shared_core.database.base import BaseModel
from sqlalchemy import DateTime, ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.models.enums import ApprovalPolicy, ApprovalStatus


class ChangeApproval(BaseModel):
    """``change_approvals`` -- one approver's step in one change's chain."""

    __tablename__ = "change_approvals"
    __table_args__ = (
        UniqueConstraint(
            "organization_id", "change_id", "level", "approver_id", name="uq_change_approval_step"
        ),
        Index("ix_change_approval_change", "organization_id", "change_id", "level"),
        Index("ix_change_approval_status", "organization_id", "status"),
    )

    change_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("change_requests.id", ondelete="CASCADE"), index=True
    )
    policy: Mapped[ApprovalPolicy] = mapped_column(String(32))
    level: Mapped[int] = mapped_column(Integer, default=1)
    """Which rung of the chain this approval sits on. Every approval at
    one level must resolve before the next level's rows are actioned --
    see ``app/approvals/engine.py``."""

    approver_id: Mapped[str] = mapped_column(String(255))
    approver_role: Mapped[str | None] = mapped_column(String(128), default=None)
    status: Mapped[ApprovalStatus] = mapped_column(
        String(32), default=ApprovalStatus.PENDING, index=True
    )

    comment: Mapped[str | None] = mapped_column(Text, default=None)
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)

    delegated_to: Mapped[str | None] = mapped_column(String(255), default=None)
    delegated_from: Mapped[str | None] = mapped_column(String(255), default=None)

    expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), default=None, index=True
    )
    """An approval nobody acts on by this moment is expired, not
    silently still pending forever -- see the approval-expiry sweep in
    ``app/workers/approval_expiry_sweep.py``."""


__all__ = ["ChangeApproval"]
