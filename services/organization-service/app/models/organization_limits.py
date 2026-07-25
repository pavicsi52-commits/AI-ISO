"""``organization_limits`` table. Per docs/033 "RESOURCE LIMITS": CPU,
Memory, Storage, Queue Usage, Concurrent Workflows, Concurrent Jobs,
Concurrent AI Tasks, Concurrent Users, Bandwidth.

Distinct from :class:`~app.models.organization_quota.OrganizationQuota`
(count-based, per-plan caps like "max users") -- these are runtime
*resource* ceilings (CPU/memory/bandwidth) enforced per request/job,
matching docs/033's own separate "QUOTAS" vs "RESOURCE LIMITS" sections.
"""

from __future__ import annotations

from shared_core.database.base import BaseModel
from sqlalchemy import ForeignKeyConstraint, Integer, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column


class OrganizationLimits(BaseModel):
    """One organization's resource ceilings."""

    __tablename__ = "organization_limits"
    __table_args__ = (
        ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        UniqueConstraint("organization_id", name="uq_organization_limits_org"),
    )

    cpu_cores: Mapped[int] = mapped_column(Integer, default=4)
    memory_mb: Mapped[int] = mapped_column(Integer, default=4096)
    storage_gb: Mapped[int] = mapped_column(Integer, default=50)
    queue_usage: Mapped[int] = mapped_column(Integer, default=1000)
    concurrent_workflows: Mapped[int] = mapped_column(Integer, default=10)
    concurrent_jobs: Mapped[int] = mapped_column(Integer, default=10)
    concurrent_ai_tasks: Mapped[int] = mapped_column(Integer, default=5)
    concurrent_users: Mapped[int] = mapped_column(Integer, default=100)
    bandwidth_mbps: Mapped[int] = mapped_column(Integer, default=100)


__all__ = ["OrganizationLimits"]
