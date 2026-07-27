"""``workflow_statistics`` table -- a cached analytics rollup for one
organization. Per docs/042 "ANALYTICS" "Collect": Workflow Count,
Execution Time, Failure Rate, Success Rate, Average Duration,
Checkpoint Count, Approval Count, Replay Count, Rollback Count, Node
Statistics, Execution Trends. Recomputed on demand and cached, the same
"cached, not live" shape ``services/playbook-service``'s own
``PlaybookStatistics`` established.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from shared_core.database.base import BaseModel
from sqlalchemy import JSON, DateTime, Float, Integer, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column


class WorkflowStatistics(BaseModel):
    """One organization's cached workflow-runtime analytics snapshot."""

    __tablename__ = "workflow_statistics"
    __table_args__ = (UniqueConstraint("organization_id", name="uq_workflow_statistics_org"),)

    total_workflows: Mapped[int] = mapped_column(Integer, default=0)
    total_executions: Mapped[int] = mapped_column(Integer, default=0)
    success_rate: Mapped[float] = mapped_column(Float, default=0.0)
    failure_rate: Mapped[float] = mapped_column(Float, default=0.0)
    average_duration_seconds: Mapped[float] = mapped_column(Float, default=0.0)
    checkpoint_count: Mapped[int] = mapped_column(Integer, default=0)
    approval_count: Mapped[int] = mapped_column(Integer, default=0)
    replay_count: Mapped[int] = mapped_column(Integer, default=0)
    rollback_count: Mapped[int] = mapped_column(Integer, default=0)
    node_statistics: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    execution_trends: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    computed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


__all__ = ["WorkflowStatistics"]
