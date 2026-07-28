"""``report_jobs`` table -- a saved, re-runnable report definition."""

from __future__ import annotations

import uuid
from typing import Any

from shared_core.database.base import BaseModel
from sqlalchemy import JSON, Boolean, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.enums import ExportFormat, ReportCategory, ReportType


class ReportJob(BaseModel):
    """One saved report ("GET /reports", "POST /reports").

    A *job* is the durable thing a user names, shares, schedules, and
    re-runs; an *execution* is one run of it. Keeping them apart is what
    lets history, favourites, and schedules all point at a stable id
    while each run gets its own row.
    """

    __tablename__ = "report_jobs"

    template_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("report_templates.id", ondelete="SET NULL"), default=None, index=True
    )
    name: Mapped[str] = mapped_column(String(255), index=True)
    description: Mapped[str | None] = mapped_column(Text, default=None)
    category: Mapped[ReportCategory] = mapped_column(String(24), index=True)
    report_type: Mapped[ReportType] = mapped_column(String(24), index=True)
    default_format: Mapped[ExportFormat] = mapped_column(String(16), default=ExportFormat.PDF)
    parameter_values: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    filters: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    owner_id: Mapped[uuid.UUID | None] = mapped_column(default=None, index=True)


__all__ = ["ReportJob"]
