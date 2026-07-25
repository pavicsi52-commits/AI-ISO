"""Response schema for ``GET /configurations/analytics``. Per docs/039
"ANALYTICS" "Collect": Profile Count, Version Count, Drift Statistics,
Compliance Scores, Rollback Statistics, Deployment Readiness,
Environment Distribution, Change Frequency.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel


class ConfigurationStatisticsResponse(BaseModel):
    """The current-state configuration-management analytics rollup."""

    total_profiles: int
    total_versions: int
    drift_statistics: dict[str, Any]
    compliance_scores: dict[str, Any]
    rollback_statistics: dict[str, Any]
    deployment_readiness: dict[str, Any]
    environment_distribution: dict[str, Any]
    change_frequency: dict[str, Any]
    computed_at: datetime


__all__ = ["ConfigurationStatisticsResponse"]
