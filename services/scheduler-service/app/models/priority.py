"""``job_priorities`` -- an organization's own priority-escalation policy.

Not a per-job setting -- one row per :class:`~app.models.enums.JobPriority`
band, per organization, the same organization-configurable-catalogue
shape ``services/change-management-service``'s ``ChangePriorityRecord``
establishes. A job queued past ``escalate_after_minutes`` at this band
escalates to ``escalate_to``; a band with no row configured never
escalates.
"""

from __future__ import annotations

from shared_core.database.base import BaseModel
from sqlalchemy import Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.models.enums import JobPriority


class JobPriorityPolicy(BaseModel):
    """``job_priorities`` -- one organization's escalation rule for one band."""

    __tablename__ = "job_priorities"
    __table_args__ = (
        UniqueConstraint("organization_id", "priority", name="uq_job_priority_policy_band"),
    )

    priority: Mapped[JobPriority] = mapped_column(String(32), index=True)
    label: Mapped[str] = mapped_column(String(128))
    color: Mapped[str | None] = mapped_column(String(32), default=None)
    escalate_after_minutes: Mapped[int | None] = mapped_column(Integer, default=None)
    escalate_to: Mapped[JobPriority | None] = mapped_column(String(32), default=None)


__all__ = ["JobPriorityPolicy"]
