"""``organization_statistics`` table. Per docs/033 "ORGANIZATION
ANALYTICS": User Count, Project Count, Asset Count, Workflow Count,
Automation Count, Validation Count, Storage Usage, API Usage, AI
Usage, License Utilization. A durable, periodically recomputed
snapshot -- one row per organization, upserted on each recompute,
mirroring ``services/rbac-service``'s ``permission_cache`` "durable
snapshot, not the hot cache" precedent.
"""

from __future__ import annotations

from datetime import datetime

from shared_core.database.base import BaseModel
from sqlalchemy import (
    BigInteger,
    DateTime,
    ForeignKeyConstraint,
    Integer,
    Numeric,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column


class OrganizationStatistics(BaseModel):
    """One organization's last-computed usage snapshot."""

    __tablename__ = "organization_statistics"
    __table_args__ = (
        ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        UniqueConstraint("organization_id", name="uq_organization_statistics_org"),
    )

    user_count: Mapped[int] = mapped_column(Integer, default=0)
    project_count: Mapped[int] = mapped_column(Integer, default=0)
    asset_count: Mapped[int] = mapped_column(Integer, default=0)
    workflow_count: Mapped[int] = mapped_column(Integer, default=0)
    automation_count: Mapped[int] = mapped_column(Integer, default=0)
    validation_count: Mapped[int] = mapped_column(Integer, default=0)
    storage_usage_bytes: Mapped[int] = mapped_column(BigInteger, default=0)
    api_usage_count: Mapped[int] = mapped_column(BigInteger, default=0)
    ai_usage_count: Mapped[int] = mapped_column(BigInteger, default=0)
    license_utilization_percent: Mapped[float] = mapped_column(Numeric(5, 2), default=0)
    computed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


__all__ = ["OrganizationStatistics"]
