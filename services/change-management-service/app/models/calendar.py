"""``change_calendar`` -- maintenance windows and blackout periods.

One table for both entry kinds, distinguished by
:class:`~app.models.enums.CalendarEntryKind`, because a scheduling
question ("is this slot open") always has to check both at once: a
window that is open for maintenance but sits inside an org-wide blackout
is not actually available.
"""

from __future__ import annotations

from datetime import datetime

from shared_core.database.base import BaseModel
from sqlalchemy import Boolean, DateTime, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.enums import CalendarEntryKind, RecurrenceKind


class ChangeCalendarEntry(BaseModel):
    """``change_calendar`` -- one maintenance window or blackout period.

    Not tied to a single change by foreign key: a recurring maintenance
    window is capacity many changes book into over time, and a blackout
    period exists precisely because it applies regardless of which
    change asks. ``ChangeRequest.calendar_entry_id`` is the one-directional
    link from a change to the window it is scheduled inside.
    """

    __tablename__ = "change_calendar"

    kind: Mapped[CalendarEntryKind] = mapped_column(String(32), index=True)
    title: Mapped[str] = mapped_column(String(255))
    description: Mapped[str | None] = mapped_column(Text, default=None)

    starts_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    ends_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    timezone: Mapped[str] = mapped_column(String(64), default="UTC")

    recurrence: Mapped[RecurrenceKind] = mapped_column(String(16), default=RecurrenceKind.NONE)
    recurrence_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)

    is_org_wide: Mapped[bool] = mapped_column(Boolean, default=True)
    capacity_limit: Mapped[int | None] = mapped_column(Integer, default=None)
    """How many changes may book into this window at once. ``None`` is
    uncapped -- a blackout period has no notion of capacity at all, and
    a maintenance window without an explicit limit is deliberately left
    open rather than defaulting to some made-up ceiling."""


__all__ = ["ChangeCalendarEntry"]
