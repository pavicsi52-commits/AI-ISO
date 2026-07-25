"""Response schema for ``GET /automation/statistics``. Per docs/040
"ANALYTICS" "Collect": Execution Count, Success Rate, Failure Rate,
Average Runtime, Resource Usage, Connector Usage, Automation Trends,
Top Failed Jobs, Most Executed Jobs, Execution Heatmaps.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel


class AutomationStatisticsResponse(BaseModel):
    """The current-state automation analytics rollup."""

    total_jobs: int
    total_executions: int
    success_rate: float
    failure_rate: float
    average_runtime_seconds: float
    resource_usage: dict[str, Any]
    connector_usage: dict[str, Any]
    top_failed_jobs: dict[str, Any]
    most_executed_jobs: dict[str, Any]
    execution_heatmap: dict[str, Any]
    computed_at: datetime


__all__ = ["AutomationStatisticsResponse"]
