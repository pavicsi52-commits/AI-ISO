"""``configuration_restore_jobs`` table. Per docs/039 "RESTORE"
"Support": Restore Profile, Restore Version, Selective Restore, Bulk
Restore, Preview Restore, Validation, Audit.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from shared_core.database.base import BaseModel
from sqlalchemy import Boolean, DateTime, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from app.models.enums import RestoreStatus, RestoreType


class ConfigurationRestoreJob(BaseModel):
    """One restore operation from a backup back onto a profile."""

    __tablename__ = "configuration_restore_jobs"

    backup_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("configuration_backups.id", ondelete="CASCADE"), nullable=False, index=True
    )
    profile_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("configuration_profiles.id", ondelete="CASCADE"), nullable=False, index=True
    )
    restore_type: Mapped[RestoreType] = mapped_column(String(16), index=True)
    status: Mapped[RestoreStatus] = mapped_column(
        String(16), default=RestoreStatus.PENDING, index=True
    )
    preview_only: Mapped[bool] = mapped_column(Boolean, default=False)
    requested_by: Mapped[uuid.UUID | None] = mapped_column(default=None)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)


__all__ = ["ConfigurationRestoreJob"]
