"""``report_templates`` table -- a versioned, approvable report definition."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from shared_core.database.base import BaseModel
from sqlalchemy import JSON, Boolean, DateTime, ForeignKey, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.models.enums import ReportCategory, ReportType, TemplateStatus


class ReportTemplate(BaseModel):
    """One report template.

    ``definition`` holds the designer document (sections, charts,
    branding) as JSON rather than a rigid column set. That is
    deliberate: docs/047's designer supports reusable sections, widgets,
    and themes whose shape is authored per template, and normalising
    that into tables would force a schema migration every time the
    designer gains a section kind. The JSON is validated on write by
    :mod:`app.reports.designer.schema`, so it is structured data, not a
    free-for-all blob.
    """

    __tablename__ = "report_templates"
    __table_args__ = (
        UniqueConstraint(
            "organization_id", "name", "version_number", name="uq_report_template_org_name_version"
        ),
    )

    category_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("report_categories.id", ondelete="SET NULL"), default=None, index=True
    )
    name: Mapped[str] = mapped_column(String(255), index=True)
    description: Mapped[str | None] = mapped_column(Text, default=None)
    category: Mapped[ReportCategory] = mapped_column(String(24), index=True)
    report_type: Mapped[ReportType] = mapped_column(String(24), index=True)
    version_number: Mapped[str] = mapped_column(String(16), default="1.0.0", index=True)
    status: Mapped[TemplateStatus] = mapped_column(
        String(16), default=TemplateStatus.DRAFT, index=True
    )
    definition: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    branding: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    is_system: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    approved_by: Mapped[uuid.UUID | None] = mapped_column(default=None)
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)


__all__ = ["ReportTemplate"]
