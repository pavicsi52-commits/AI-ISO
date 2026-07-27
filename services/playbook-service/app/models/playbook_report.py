"""``playbook_reports`` table. Per docs/041 "REPORTING" "Generate":
Repository Reports, Validation Reports, Approval Reports, Version
Reports, Dependency Reports, Executive Dashboards.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from shared_core.database.base import BaseModel
from sqlalchemy import JSON, DateTime, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from app.models.enums import PlaybookReportType


class PlaybookReport(BaseModel):
    """One generated playbook-repository report."""

    __tablename__ = "playbook_reports"

    playbook_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("playbooks.id", ondelete="SET NULL"), default=None, index=True
    )
    report_type: Mapped[PlaybookReportType] = mapped_column(String(24), index=True)
    generated_by: Mapped[uuid.UUID | None] = mapped_column(default=None)
    parameters: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    result: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    generated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


__all__ = ["PlaybookReport"]
