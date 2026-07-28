"""``dashboard_widget_settings`` table -- per-user widget overrides."""

from __future__ import annotations

import uuid
from typing import Any

from shared_core.database.base import BaseModel
from sqlalchemy import JSON, Boolean, ForeignKey, Integer, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column


class DashboardWidgetSetting(BaseModel):
    """One user's own overrides for one widget.

    Separate from :class:`~app.models.dashboard_widget.DashboardWidget`
    because a shared dashboard has one definition but many viewers: one
    person collapsing a widget or slowing its refresh must not change
    what everyone else sees.
    """

    __tablename__ = "dashboard_widget_settings"
    __table_args__ = (
        UniqueConstraint("widget_id", "user_id", name="uq_widget_setting_widget_user"),
    )

    widget_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("dashboard_widgets.id", ondelete="CASCADE"), index=True
    )
    user_id: Mapped[uuid.UUID] = mapped_column(index=True)
    collapsed: Mapped[bool] = mapped_column(Boolean, default=False)
    hidden: Mapped[bool] = mapped_column(Boolean, default=False)
    refresh_seconds_override: Mapped[int | None] = mapped_column(Integer, default=None)
    options_override: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)


__all__ = ["DashboardWidgetSetting"]
