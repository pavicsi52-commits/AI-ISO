"""``monitoring_reports`` table -- a generated report. ``target_id`` is
nullable because some report types (``CAPACITY``, ``EXECUTIVE``) are
organization-wide rollups spanning many targets, not one specific one --
matching ``services/validation-service``'s own ``ValidationReport
.execution_id``-nullable precedent for the identical "most report
types are scoped, some are organization-wide" shape.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from shared_core.database.base import BaseModel
from sqlalchemy import JSON, DateTime, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from app.models.enums import MonitoringReportType


class MonitoringReport(BaseModel):
    """A generated monitoring report."""

    __tablename__ = "monitoring_reports"

    target_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("monitoring_targets.id", ondelete="SET NULL"), default=None, index=True
    )
    report_type: Mapped[MonitoringReportType] = mapped_column(String(16), index=True)
    generated_by: Mapped[uuid.UUID | None] = mapped_column(default=None)
    parameters: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    result: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    generated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


__all__ = ["MonitoringReport"]
