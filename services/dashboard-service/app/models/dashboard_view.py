"""``dashboard_views`` table -- one recorded viewing of a dashboard."""

from __future__ import annotations

import uuid
from datetime import datetime

from shared_core.database.base import BaseModel
from sqlalchemy import DateTime, Float, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column


class DashboardView(BaseModel):
    """One view ("ANALYTICS": Dashboard Views, Load Time).

    Recorded per view rather than as a counter so "most viewed *this
    week*" stays answerable; the aggregate counter lives on
    :class:`~app.models.dashboard_statistics.DashboardStatistics`.
    """

    __tablename__ = "dashboard_views"

    dashboard_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("dashboards.id", ondelete="CASCADE"), index=True
    )
    user_id: Mapped[uuid.UUID | None] = mapped_column(default=None, index=True)
    load_ms: Mapped[float | None] = mapped_column(Float, default=None)
    widget_count: Mapped[int] = mapped_column(Integer, default=0)
    failed_widget_count: Mapped[int] = mapped_column(Integer, default=0)
    client: Mapped[str | None] = mapped_column(String(255), default=None)
    viewed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)


__all__ = ["DashboardView"]
