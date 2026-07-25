"""``configuration_rollbacks`` table. Per docs/039 "ROLLBACK"
"Support": Version Rollback, Incremental Rollback, Full Rollback,
Rollback Validation, Approval Workflow, Rollback History.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from shared_core.database.base import BaseModel
from sqlalchemy import DateTime, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from app.models.enums import RollbackStatus, RollbackType


class ConfigurationRollback(BaseModel):
    """One rollback operation from a profile's current version to a prior one."""

    __tablename__ = "configuration_rollbacks"

    profile_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("configuration_profiles.id", ondelete="CASCADE"), nullable=False, index=True
    )
    from_version_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("configuration_versions.id", ondelete="SET NULL"), default=None
    )
    to_version_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("configuration_versions.id", ondelete="CASCADE"), nullable=False
    )
    rollback_type: Mapped[RollbackType] = mapped_column(String(16), index=True)
    status: Mapped[RollbackStatus] = mapped_column(
        String(16), default=RollbackStatus.PENDING, index=True
    )
    requested_by: Mapped[uuid.UUID | None] = mapped_column(default=None)
    approved_by: Mapped[uuid.UUID | None] = mapped_column(default=None)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
    reason: Mapped[str | None] = mapped_column(String(1024), default=None)


__all__ = ["ConfigurationRollback"]
