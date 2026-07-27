"""``playbook_versions`` table. Per docs/041 "VERSIONING" "Support":
Semantic Versioning, Version History, Rollback, Diff, Comparison,
Release Notes, Change Tracking, Approval Per Version.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from shared_core.database.base import BaseModel
from sqlalchemy import DateTime, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column


class PlaybookVersion(BaseModel):
    """One immutable content snapshot of a playbook."""

    __tablename__ = "playbook_versions"

    playbook_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("playbooks.id", ondelete="CASCADE"), nullable=False, index=True
    )
    version_number: Mapped[str] = mapped_column(String(32), index=True)
    content: Mapped[str] = mapped_column(Text)
    checksum: Mapped[str] = mapped_column(String(64), index=True)
    release_notes: Mapped[str | None] = mapped_column(Text, default=None)
    change_summary: Mapped[str | None] = mapped_column(String(2048), default=None)
    changed_by: Mapped[uuid.UUID | None] = mapped_column(default=None)
    approved_by: Mapped[uuid.UUID | None] = mapped_column(default=None)
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)


__all__ = ["PlaybookVersion"]
