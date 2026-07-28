"""``dashboard_themes`` table -- palettes and branding."""

from __future__ import annotations

from typing import Any

from shared_core.database.base import BaseModel
from sqlalchemy import JSON, Boolean, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.models.enums import ThemeMode


class DashboardTheme(BaseModel):
    """One theme.

    ``palette`` and ``branding`` are JSON because a theme's shape is
    authored, not fixed: adding an accent colour should not require a
    schema migration. Both are validated on write by
    :mod:`app.themes.schema`.
    """

    __tablename__ = "dashboard_themes"
    __table_args__ = (UniqueConstraint("organization_id", "slug", name="uq_dashboard_theme_slug"),)

    slug: Mapped[str] = mapped_column(String(64), index=True)
    name: Mapped[str] = mapped_column(String(255))
    description: Mapped[str | None] = mapped_column(Text, default=None)
    mode: Mapped[ThemeMode] = mapped_column(String(16), default=ThemeMode.LIGHT, index=True)
    palette: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    branding: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    accessibility: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    """High-contrast, reduced-motion, and minimum font size.

    Accessibility is stored with the theme rather than as a user
    preference because a corporate theme can be non-compliant on its
    own, and the fix belongs where the colours are chosen.
    """

    is_system: Mapped[bool] = mapped_column(Boolean, default=False, index=True)


__all__ = ["DashboardTheme"]
