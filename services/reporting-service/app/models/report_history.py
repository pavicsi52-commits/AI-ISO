"""``report_history`` table -- the user-facing activity trail."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from shared_core.database.base import BaseModel
from sqlalchemy import JSON, DateTime, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column


class ReportHistory(BaseModel):
    """One entry in a report's own visible history.

    Deliberately distinct from :class:`app.models.report_audit
    .ReportAudit`. History is what a *user* sees on a report -- "you ran
    this on Tuesday, it produced 412 rows" -- and is safe to show
    broadly. Audit is the security record of who changed what, is never
    edited, and answers to a different audience. Collapsing them would
    force one of the two to compromise.
    """

    __tablename__ = "report_history"

    job_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("report_jobs.id", ondelete="CASCADE"), index=True
    )
    execution_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("report_executions.id", ondelete="SET NULL"), default=None, index=True
    )
    event: Mapped[str] = mapped_column(String(64), index=True)
    summary: Mapped[str] = mapped_column(String(1024))
    details: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    actor_id: Mapped[uuid.UUID | None] = mapped_column(default=None, index=True)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)


__all__ = ["ReportHistory"]
