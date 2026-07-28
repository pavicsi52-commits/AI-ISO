"""``dashboard_widgets`` table -- one widget on one dashboard."""

from __future__ import annotations

import uuid
from typing import Any

from shared_core.database.base import BaseModel
from sqlalchemy import JSON, Boolean, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.models.enums import DataSource, RefreshMode, WidgetType


class DashboardWidget(BaseModel):
    """One widget.

    The widget owns *what* it shows (type, query, options); its
    *placement* lives in :class:`app.models.dashboard_layout
    .DashboardLayout`. Keeping those apart is what lets one widget
    occupy different positions per breakpoint without duplicating its
    definition.
    """

    __tablename__ = "dashboard_widgets"
    __table_args__ = (
        UniqueConstraint("dashboard_id", "widget_key", name="uq_dashboard_widget_key"),
    )

    dashboard_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("dashboards.id", ondelete="CASCADE"), index=True
    )
    widget_key: Mapped[str] = mapped_column(String(64), index=True)
    title: Mapped[str] = mapped_column(String(255))
    description: Mapped[str | None] = mapped_column(Text, default=None)
    widget_type: Mapped[WidgetType] = mapped_column(String(24), index=True)
    data_source: Mapped[DataSource] = mapped_column(
        String(24), default=DataSource.STATIC, index=True
    )
    query: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    options: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    filters: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)
    refresh_mode: Mapped[RefreshMode] = mapped_column(String(16), default=RefreshMode.POLLING)
    refresh_seconds: Mapped[int] = mapped_column(Integer, default=60)
    cache_seconds: Mapped[int] = mapped_column(Integer, default=30)
    """How long a resolved payload may be reused ("Widget Caching").

    Per widget rather than global: an alert feed and a capacity chart
    have genuinely different staleness tolerances.
    """

    display_order: Mapped[int] = mapped_column(Integer, default=0)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, index=True)


__all__ = ["DashboardWidget"]
