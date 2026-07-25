"""``organization_branding`` table. Per docs/033 "BRANDING": Logo, Dark
Logo, Favicon, Primary Color, Secondary Color, Theme, Email Templates,
Login Screen Branding, Dashboard Branding.
"""

from __future__ import annotations

from typing import Any

from shared_core.database.base import BaseModel
from sqlalchemy import JSON, ForeignKeyConstraint, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column


class OrganizationBranding(BaseModel):
    """One organization's white-label branding configuration."""

    __tablename__ = "organization_branding"
    __table_args__ = (
        ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        UniqueConstraint("organization_id", name="uq_organization_branding_org"),
    )

    logo_url: Mapped[str | None] = mapped_column(String(1024), default=None)
    dark_logo_url: Mapped[str | None] = mapped_column(String(1024), default=None)
    favicon_url: Mapped[str | None] = mapped_column(String(1024), default=None)
    primary_color: Mapped[str | None] = mapped_column(String(16), default=None)
    secondary_color: Mapped[str | None] = mapped_column(String(16), default=None)
    theme: Mapped[str] = mapped_column(String(32), default="light")
    email_templates: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    login_screen_branding: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    dashboard_branding: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)


__all__ = ["OrganizationBranding"]
