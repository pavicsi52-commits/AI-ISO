"""``dashboard_favorites`` table -- a user's own pinned dashboards."""

from __future__ import annotations

import uuid

from shared_core.database.base import BaseModel
from sqlalchemy import ForeignKey, Integer, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column


class DashboardFavorite(BaseModel):
    """One user's favourite dashboard.

    The unique constraint makes favouriting twice idempotent at the
    database level rather than relying on every caller to check first.
    """

    __tablename__ = "dashboard_favorites"
    __table_args__ = (
        UniqueConstraint("user_id", "dashboard_id", name="uq_dashboard_favorite_user"),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(index=True)
    dashboard_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("dashboards.id", ondelete="CASCADE"), index=True
    )
    display_order: Mapped[int] = mapped_column(Integer, default=0)


__all__ = ["DashboardFavorite"]
