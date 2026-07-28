"""``alert_reports`` table -- a generated report. ``alert_id`` is
nullable because most report types (Executive, Operational, SLA,
Trend, Noise Analysis) are organization-wide rollups, not scoped to
one specific alert, matching
``services/monitoring-service``'s own ``MonitoringReport.target_id``
-nullable precedent for the identical "most report types are
org-wide, one type is scoped" shape.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from shared_core.database.base import BaseModel
from sqlalchemy import JSON, DateTime, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from app.models.enums import AlertReportType


class AlertReport(BaseModel):
    """A generated alerting report."""

    __tablename__ = "alert_reports"

    alert_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("alert_instances.id", ondelete="SET NULL"), default=None, index=True
    )
    report_type: Mapped[AlertReportType] = mapped_column(String(16), index=True)
    generated_by: Mapped[uuid.UUID | None] = mapped_column(default=None)
    parameters: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    result: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    generated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


__all__ = ["AlertReport"]
