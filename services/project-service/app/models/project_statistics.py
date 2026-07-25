"""``project_statistics`` table. Per docs/034 "PROJECT ANALYTICS": Member
Count, Automation Count, Workflow Count, Validation Count, Inventory
Count, Connector Count, AI Usage, Storage Usage, Execution Statistics,
Failure Rates, Success Rates.

Only ``member_count`` (this service's own
:class:`~app.models.project_member.ProjectMember` rows) is computed
from real data this service owns. Every other count belongs to
services docs/034 explicitly excludes from this prompt's scope
("DO NOT IMPLEMENT": Inventory, Discovery, Automation, Workflow
Runtime, Validation, Monitoring, Secrets) and that don't exist yet in
this build -- those fields are honestly left at ``0`` rather than
fabricated, the same honesty precedent
``services/organization-service``'s own ``OrganizationStatistics``
established (itself following ``services/user-management-service``'s
"Virus Scan Hook" precedent).
"""

from __future__ import annotations

import uuid
from datetime import datetime

from shared_core.database.base import BaseModel
from sqlalchemy import DateTime, ForeignKey, Integer, Numeric, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column


class ProjectStatistics(BaseModel):
    """One project's last-computed usage snapshot."""

    __tablename__ = "project_statistics"
    __table_args__ = (UniqueConstraint("project_id", name="uq_project_statistics_project"),)

    project_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True
    )

    member_count: Mapped[int] = mapped_column(Integer, default=0)
    automation_count: Mapped[int] = mapped_column(Integer, default=0)
    workflow_count: Mapped[int] = mapped_column(Integer, default=0)
    validation_count: Mapped[int] = mapped_column(Integer, default=0)
    inventory_count: Mapped[int] = mapped_column(Integer, default=0)
    connector_count: Mapped[int] = mapped_column(Integer, default=0)
    ai_usage_count: Mapped[int] = mapped_column(Integer, default=0)
    storage_usage_bytes: Mapped[int] = mapped_column(Integer, default=0)
    execution_count: Mapped[int] = mapped_column(Integer, default=0)
    failure_count: Mapped[int] = mapped_column(Integer, default=0)
    success_count: Mapped[int] = mapped_column(Integer, default=0)
    success_rate_percent: Mapped[float] = mapped_column(Numeric(5, 2), default=0)
    computed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


__all__ = ["ProjectStatistics"]
