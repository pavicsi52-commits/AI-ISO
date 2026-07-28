"""``dashboard_statistics`` table -- one analytics rollup per organization."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from shared_core.database.base import BaseModel
from sqlalchemy import JSON, DateTime, Float, Integer
from sqlalchemy.orm import Mapped, mapped_column


class DashboardStatistics(BaseModel):
    """An organization's own dashboard analytics.

    One row per organization, updated in place. The per-view history
    any trend would be computed from already lives in
    :class:`~app.models.dashboard_view.DashboardView`.
    """

    __tablename__ = "dashboard_statistics"

    total_dashboards: Mapped[int] = mapped_column(Integer, default=0)
    total_widgets: Mapped[int] = mapped_column(Integer, default=0)
    total_views: Mapped[int] = mapped_column(Integer, default=0)
    unique_viewers: Mapped[int] = mapped_column(Integer, default=0)
    total_shares: Mapped[int] = mapped_column(Integer, default=0)
    average_load_ms: Mapped[float] = mapped_column(Float, default=0.0)
    widget_failure_rate: Mapped[float] = mapped_column(Float, default=0.0)
    most_viewed: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    widget_usage: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    dashboard_type_usage: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    refresh_usage: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    computed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)


__all__ = ["DashboardStatistics"]
