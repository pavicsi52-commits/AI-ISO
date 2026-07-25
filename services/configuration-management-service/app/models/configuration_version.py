"""``configuration_versions`` table. Per docs/039 "VERSIONING"
"Support": Semantic Versioning, Configuration History, Version
Comparison, Rollback, Branching, Change Tracking, Approval Workflow.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from shared_core.database.base import BaseModel
from sqlalchemy import JSON, DateTime, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column


class ConfigurationVersion(BaseModel):
    """One immutable snapshot of a profile's full desired state."""

    __tablename__ = "configuration_versions"

    profile_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("configuration_profiles.id", ondelete="CASCADE"), nullable=False, index=True
    )
    version_number: Mapped[str] = mapped_column(String(32), index=True)
    branch: Mapped[str] = mapped_column(String(128), default="main", index=True)
    content: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    change_summary: Mapped[str | None] = mapped_column(String(2048), default=None)
    changed_by: Mapped[uuid.UUID | None] = mapped_column(default=None)
    approved_by: Mapped[uuid.UUID | None] = mapped_column(default=None)
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)


__all__ = ["ConfigurationVersion"]
