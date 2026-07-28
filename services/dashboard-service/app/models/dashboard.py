"""``dashboards`` table -- one dashboard definition."""

from __future__ import annotations

import uuid
from typing import Any

from shared_core.database.base import BaseModel
from sqlalchemy import JSON, Boolean, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.models.enums import DashboardType, DashboardVisibility


class Dashboard(BaseModel):
    """One dashboard.

    ``slug`` is unique per organization so a dashboard can be addressed
    by a stable human-readable name in a URL, independently of its id.

    Note the deliberate absence of an ``is_active``/``version`` of its
    own: :class:`BaseModel` already owns both, and redeclaring either
    would silently repurpose the platform's soft-delete flag or its
    optimistic-lock counter. That collision has shipped as a live bug
    twice in this platform; ``layout_revision`` below is named to avoid
    it.
    """

    __tablename__ = "dashboards"
    __table_args__ = (UniqueConstraint("organization_id", "slug", name="uq_dashboard_org_slug"),)

    slug: Mapped[str] = mapped_column(String(128), index=True)
    name: Mapped[str] = mapped_column(String(255), index=True)
    description: Mapped[str | None] = mapped_column(Text, default=None)
    dashboard_type: Mapped[DashboardType] = mapped_column(String(24), index=True)
    visibility: Mapped[DashboardVisibility] = mapped_column(
        String(16), default=DashboardVisibility.PRIVATE, index=True
    )
    theme_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("dashboard_themes.id", ondelete="SET NULL"), default=None, index=True
    )
    owner_id: Mapped[uuid.UUID | None] = mapped_column(default=None, index=True)
    default_filters: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)
    refresh_seconds: Mapped[int] = mapped_column(Integer, default=0)
    """Auto-refresh cadence; ``0`` means manual only."""

    layout_revision: Mapped[int] = mapped_column(Integer, default=1)
    """Monotonic revision of the *layout*, for undo/redo and history.

    Deliberately **not** named ``version``: that name belongs to
    :class:`BaseModel`'s optimistic-locking column, which
    ``BaseRepository.update()`` increments on every write.
    """

    enabled: Mapped[bool] = mapped_column(Boolean, default=True, index=True)


__all__ = ["Dashboard"]
