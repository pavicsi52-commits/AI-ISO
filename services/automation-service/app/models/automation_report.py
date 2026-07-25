"""``automation_reports`` table. Per docs/040 "REPORTING" "Generate":
Execution Reports, Failure Reports, Success Reports, Performance
Reports, Compliance Reports, Executive Dashboards, Automation Trends.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from shared_core.database.base import BaseModel
from sqlalchemy import JSON, DateTime, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from app.models.enums import AutomationReportType


class AutomationReport(BaseModel):
    """One generated automation report."""

    __tablename__ = "automation_reports"

    job_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("automation_jobs.id", ondelete="SET NULL"), default=None, index=True
    )
    report_type: Mapped[AutomationReportType] = mapped_column(String(24), index=True)
    generated_by: Mapped[uuid.UUID | None] = mapped_column(default=None)
    parameters: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    result: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    generated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


__all__ = ["AutomationReport"]
