"""``organization_quotas`` table. Per docs/033 "QUOTAS": Maximum Users,
Projects, Assets, Storage, Workflows, Automation Jobs, Connectors, API
Calls, AI Requests, Plugins. "Configurable per organization."
"""

from __future__ import annotations

from shared_core.database.base import BaseModel
from sqlalchemy import ForeignKeyConstraint, Integer, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column


class OrganizationQuota(BaseModel):
    """One organization's configured count-based quotas."""

    __tablename__ = "organization_quotas"
    __table_args__ = (
        ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        UniqueConstraint("organization_id", name="uq_organization_quota_org"),
    )

    max_users: Mapped[int] = mapped_column(Integer, default=10)
    max_projects: Mapped[int] = mapped_column(Integer, default=5)
    max_assets: Mapped[int] = mapped_column(Integer, default=1000)
    max_storage_gb: Mapped[int] = mapped_column(Integer, default=50)
    max_workflows: Mapped[int] = mapped_column(Integer, default=20)
    max_automation_jobs: Mapped[int] = mapped_column(Integer, default=50)
    max_connectors: Mapped[int] = mapped_column(Integer, default=10)
    max_api_calls_per_day: Mapped[int] = mapped_column(Integer, default=10_000)
    max_ai_requests_per_day: Mapped[int] = mapped_column(Integer, default=1_000)
    max_plugins: Mapped[int] = mapped_column(Integer, default=10)


__all__ = ["OrganizationQuota"]
