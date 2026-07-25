"""``project_archives`` table -- a record of each archive/restore cycle a
project goes through. Per docs/034 "PROJECT LIFECYCLE": Archive, Restore.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from shared_core.database.base import BaseModel
from sqlalchemy import JSON, DateTime, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column


class ProjectArchive(BaseModel):
    """One archive event for a project, and its eventual restore if any."""

    __tablename__ = "project_archives"

    project_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True
    )

    archived_by: Mapped[uuid.UUID | None] = mapped_column(default=None)
    reason: Mapped[str | None] = mapped_column(String(1024), default=None)
    archived_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    restored_by: Mapped[uuid.UUID | None] = mapped_column(default=None)
    restored_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
    snapshot: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)


__all__ = ["ProjectArchive"]
