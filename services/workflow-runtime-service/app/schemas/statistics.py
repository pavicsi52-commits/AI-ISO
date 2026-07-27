"""Response schema for :class:`~app.models.workflow_statistics.WorkflowStatistics`,
backing ``GET /workflow/statistics``.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel


class WorkflowStatisticsResponse(BaseModel):
    """One organization's cached workflow-runtime analytics snapshot."""

    total_workflows: int
    total_executions: int
    success_rate: float
    failure_rate: float
    average_duration_seconds: float
    checkpoint_count: int
    approval_count: int
    replay_count: int
    rollback_count: int
    node_statistics: dict[str, Any]
    execution_trends: dict[str, Any]
    computed_at: datetime


__all__ = ["WorkflowStatisticsResponse"]
