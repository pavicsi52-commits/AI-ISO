"""``dashboard_history`` table -- the user-facing activity trail."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from shared_core.database.base import BaseModel
from sqlalchemy import JSON, DateTime, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column


class DashboardHistory(BaseModel):
    """One entry in a dashboard's visible history.

    Deliberately distinct from
    :class:`~app.models.dashboard_audit.DashboardAudit`: history is
    what a *user* sees on a dashboard ("you rearranged this on
    Tuesday") and is safe to show broadly, while audit is the security
    record of who changed what and answers to a different audience.

    ``layout_revision`` lets the undo/redo UI offer "restore to what it
    looked like before this change" without re-deriving it.
    """

    __tablename__ = "dashboard_history"

    dashboard_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("dashboards.id", ondelete="CASCADE"), index=True
    )
    event: Mapped[str] = mapped_column(String(64), index=True)
    summary: Mapped[str] = mapped_column(String(1024))
    details: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    layout_revision: Mapped[int | None] = mapped_column(Integer, default=None)
    actor_id: Mapped[uuid.UUID | None] = mapped_column(default=None, index=True)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)


__all__ = ["DashboardHistory"]
