"""``configuration_approvals`` table. Per docs/039 "APPROVALS"
"Support": Approval Workflow, Multi-Level Approval, Approval History,
Comments, Rejection, Resubmission, Notifications.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from shared_core.database.base import BaseModel
from sqlalchemy import DateTime, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.models.enums import ApprovalStatus


class ConfigurationApproval(BaseModel):
    """One approval-workflow step against a profile, version, or rollback."""

    __tablename__ = "configuration_approvals"

    profile_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("configuration_profiles.id", ondelete="CASCADE"), default=None, index=True
    )
    version_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("configuration_versions.id", ondelete="CASCADE"), default=None, index=True
    )
    rollback_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("configuration_rollbacks.id", ondelete="CASCADE"), default=None, index=True
    )
    status: Mapped[ApprovalStatus] = mapped_column(
        String(16), default=ApprovalStatus.PENDING, index=True
    )
    level: Mapped[int] = mapped_column(Integer, default=1)
    requested_by: Mapped[uuid.UUID | None] = mapped_column(default=None)
    approver_id: Mapped[uuid.UUID | None] = mapped_column(default=None)
    comments: Mapped[str | None] = mapped_column(String(2048), default=None)
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)


__all__ = ["ConfigurationApproval"]
