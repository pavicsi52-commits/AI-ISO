"""``workflow_reports`` table. Per docs/042 "REPORTING" "Generate":
Execution Reports, Performance Reports, Failure Reports, Approval
Reports, Workflow History, Executive Dashboards. Matches the
"GET-as-generate" precedent
``services/configuration-management-service``'s/
``services/playbook-service``'s own report services established: a
report is computed and persisted the moment it's requested, not queued
for later.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from shared_core.database.base import BaseModel
from sqlalchemy import JSON, DateTime, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from app.models.enums import WorkflowReportType


class WorkflowReport(BaseModel):
    """One generated workflow-runtime report."""

    __tablename__ = "workflow_reports"

    instance_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("workflow_instances.id", ondelete="SET NULL"), default=None, index=True
    )
    report_type: Mapped[WorkflowReportType] = mapped_column(String(24), index=True)
    generated_by: Mapped[uuid.UUID | None] = mapped_column(default=None)
    parameters: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    result: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    generated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


__all__ = ["WorkflowReport"]
