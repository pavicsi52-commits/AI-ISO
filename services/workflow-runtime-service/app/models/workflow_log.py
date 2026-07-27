"""``workflow_logs`` table -- structured log lines for a workflow
instance, backing ``GET /workflow-instances/{id}/logs`` (docs/042's own
literal REST list).
"""

from __future__ import annotations

import uuid
from datetime import datetime

from shared_core.database.base import BaseModel
from sqlalchemy import DateTime, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column


class WorkflowLog(BaseModel):
    """One structured log line recorded during a workflow instance's own run."""

    __tablename__ = "workflow_logs"

    instance_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("workflow_instances.id", ondelete="CASCADE"), nullable=False, index=True
    )
    node_id: Mapped[str | None] = mapped_column(String(255), default=None)
    level: Mapped[str] = mapped_column(String(16), default="info")
    message: Mapped[str] = mapped_column(Text)
    logged_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


__all__ = ["WorkflowLog"]
