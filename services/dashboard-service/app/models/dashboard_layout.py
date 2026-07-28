"""``dashboard_layouts`` table -- a versioned widget arrangement."""

from __future__ import annotations

import uuid
from typing import Any

from shared_core.database.base import BaseModel
from sqlalchemy import JSON, Boolean, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.models.enums import LayoutBreakpoint


class DashboardLayout(BaseModel):
    """One saved arrangement of widgets, for one breakpoint.

    **Every save is a new row, never an edit.** That is what makes
    undo/redo and "Saved Layouts" real: restoring is pointing
    ``is_current`` at an earlier revision, so the arrangement a user
    liked still exists exactly as it was rather than having been
    overwritten.

    ``placements`` is JSON -- a grid of ``{widget_key, x, y, w, h}`` --
    because the shape is authored per layout and normalising it would
    turn "give me this layout" into a join over hundreds of rows.
    Validated on write by :mod:`app.layouts.grid`.
    """

    __tablename__ = "dashboard_layouts"
    __table_args__ = (
        UniqueConstraint(
            "dashboard_id", "breakpoint", "revision", name="uq_layout_dashboard_bp_revision"
        ),
    )

    dashboard_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("dashboards.id", ondelete="CASCADE"), index=True
    )
    breakpoint: Mapped[LayoutBreakpoint] = mapped_column(
        String(16), default=LayoutBreakpoint.DESKTOP, index=True
    )
    revision: Mapped[int] = mapped_column(Integer, default=1, index=True)
    """This arrangement's own revision number.

    Deliberately **not** ``version``: that name belongs to
    :class:`BaseModel`'s optimistic-locking column.
    """

    name: Mapped[str | None] = mapped_column(String(255), default=None)
    columns: Mapped[int] = mapped_column(Integer, default=12)
    row_height: Mapped[int] = mapped_column(Integer, default=60)
    placements: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)
    is_current: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    created_by_user: Mapped[uuid.UUID | None] = mapped_column(default=None, index=True)


__all__ = ["DashboardLayout"]
