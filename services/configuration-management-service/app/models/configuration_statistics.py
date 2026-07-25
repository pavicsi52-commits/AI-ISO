"""``configuration_statistics`` table -- a cached analytics rollup for
one organization. Per docs/039 "ANALYTICS" "Collect": Profile Count,
Version Count, Drift Statistics, Compliance Scores, Rollback
Statistics, Deployment Readiness, Environment Distribution, Change
Frequency. Recomputed periodically rather than aggregated live on
every request, matching ``services/asset-management-service``'s own
``asset_statistics``.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from shared_core.database.base import BaseModel
from sqlalchemy import JSON, DateTime, Integer, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column


class ConfigurationStatistics(BaseModel):
    """One organization's cached configuration-management analytics snapshot."""

    __tablename__ = "configuration_statistics"
    __table_args__ = (UniqueConstraint("organization_id", name="uq_configuration_statistics_org"),)

    total_profiles: Mapped[int] = mapped_column(Integer, default=0)
    total_versions: Mapped[int] = mapped_column(Integer, default=0)
    drift_statistics: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    compliance_scores: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    rollback_statistics: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    deployment_readiness: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    environment_distribution: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    change_frequency: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    computed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


__all__ = ["ConfigurationStatistics"]
