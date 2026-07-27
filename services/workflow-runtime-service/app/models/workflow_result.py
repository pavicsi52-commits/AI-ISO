"""``workflow_results`` table -- the final outcome of one workflow
instance, written once the run terminates (``COMPLETED``/``FAILED``/
``CANCELLED``/``ROLLED_BACK``).
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from shared_core.database.base import BaseModel
from sqlalchemy import JSON, Boolean, DateTime, ForeignKey, Text
from sqlalchemy.orm import Mapped, mapped_column


class WorkflowResult(BaseModel):
    """One workflow instance's own final outcome."""

    __tablename__ = "workflow_results"

    instance_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("workflow_instances.id", ondelete="CASCADE"), nullable=False, index=True
    )
    success: Mapped[bool] = mapped_column(Boolean)
    summary: Mapped[str | None] = mapped_column(Text, default=None)
    output: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    completed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


__all__ = ["WorkflowResult"]
