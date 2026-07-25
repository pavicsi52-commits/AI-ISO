"""``automation_statistics`` table -- a cached analytics rollup for one
organization. Per docs/040 "ANALYTICS" "Collect": Execution Count,
Success Rate, Failure Rate, Average Runtime, Resource Usage, Connector
Usage, Automation Trends, Top Failed Jobs, Most Executed Jobs,
Execution Heatmaps. Recomputed periodically rather than aggregated
live on every request, matching
``services/configuration-management-service``'s own
``configuration_statistics``.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from shared_core.database.base import BaseModel
from sqlalchemy import JSON, DateTime, Float, Integer, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column


class AutomationStatistics(BaseModel):
    """One organization's cached automation analytics snapshot."""

    __tablename__ = "automation_statistics"
    __table_args__ = (UniqueConstraint("organization_id", name="uq_automation_statistics_org"),)

    total_jobs: Mapped[int] = mapped_column(Integer, default=0)
    total_executions: Mapped[int] = mapped_column(Integer, default=0)
    success_rate: Mapped[float] = mapped_column(Float, default=0.0)
    failure_rate: Mapped[float] = mapped_column(Float, default=0.0)
    average_runtime_seconds: Mapped[float] = mapped_column(Float, default=0.0)
    resource_usage: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    connector_usage: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    top_failed_jobs: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    most_executed_jobs: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    execution_heatmap: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    computed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


__all__ = ["AutomationStatistics"]
