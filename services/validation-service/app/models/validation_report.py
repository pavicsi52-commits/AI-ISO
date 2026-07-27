"""``validation_reports`` table -- a generated report. ``execution_id``
is nullable because some report types (``TREND``, ``EXECUTIVE``) are
organization-wide rollups spanning many executions, not one specific
run -- matching ``services/workflow-runtime-service``'s own
``WorkflowReport.instance_id``-nullable precedent for the identical
"most report types are scoped, some are organization-wide" shape.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from shared_core.database.base import BaseModel
from sqlalchemy import JSON, DateTime, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from app.models.enums import ValidationReportType


class ValidationReport(BaseModel):
    """A generated validation report."""

    __tablename__ = "validation_reports"

    execution_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("validation_executions.id", ondelete="SET NULL"), default=None, index=True
    )
    report_type: Mapped[ValidationReportType] = mapped_column(String(24), index=True)
    generated_by: Mapped[uuid.UUID | None] = mapped_column(default=None)
    parameters: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    result: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    generated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


__all__ = ["ValidationReport"]
