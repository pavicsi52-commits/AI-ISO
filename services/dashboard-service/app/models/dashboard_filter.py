"""``dashboard_filters`` table -- a saved filter set."""

from __future__ import annotations

import uuid
from typing import Any

from shared_core.database.base import BaseModel
from sqlalchemy import JSON, Boolean, ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column


class DashboardFilter(BaseModel):
    """One saved filter set ("Saved Filters").

    ``user_id`` is nullable: a filter saved with no user is a shared
    preset for the dashboard, while one with a user is that person's
    own. Two rows can therefore carry the same name without colliding,
    which the unique constraint reflects.
    """

    __tablename__ = "dashboard_filters"
    __table_args__ = (
        UniqueConstraint("dashboard_id", "user_id", "name", name="uq_dashboard_filter_name"),
    )

    dashboard_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("dashboards.id", ondelete="CASCADE"), index=True
    )
    user_id: Mapped[uuid.UUID | None] = mapped_column(default=None, index=True)
    name: Mapped[str] = mapped_column(String(255))
    clauses: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)
    is_default: Mapped[bool] = mapped_column(Boolean, default=False)


__all__ = ["DashboardFilter"]
