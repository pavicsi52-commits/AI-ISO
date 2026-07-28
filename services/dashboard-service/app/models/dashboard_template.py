"""``dashboard_templates`` table -- a reusable dashboard blueprint."""

from __future__ import annotations

from typing import Any

from shared_core.database.base import BaseModel
from sqlalchemy import JSON, Boolean, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.models.enums import DashboardType


class DashboardTemplate(BaseModel):
    """One template ("Template Library").

    ``definition`` carries the widgets and layout a template
    instantiates, validated on write by
    :mod:`app.templates.schema`, so applying a template cannot produce
    a dashboard that fails to render.
    """

    __tablename__ = "dashboard_templates"
    __table_args__ = (
        UniqueConstraint("organization_id", "slug", name="uq_dashboard_template_slug"),
    )

    slug: Mapped[str] = mapped_column(String(128), index=True)
    name: Mapped[str] = mapped_column(String(255), index=True)
    description: Mapped[str | None] = mapped_column(Text, default=None)
    dashboard_type: Mapped[DashboardType] = mapped_column(String(24), index=True)
    definition: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    is_system: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    applied_count: Mapped[int] = mapped_column(Integer, default=0)


__all__ = ["DashboardTemplate"]
