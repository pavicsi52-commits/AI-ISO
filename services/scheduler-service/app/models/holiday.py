"""``holiday_calendars`` -- dates ``BUSINESS_DAYS``-aware scheduling treats as non-working."""

from __future__ import annotations

from datetime import date

from shared_core.database.base import BaseModel
from sqlalchemy import Boolean, Date, Index, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.enums import HolidayScope


class HolidayCalendarEntry(BaseModel):
    """``holiday_calendars`` -- one non-working day."""

    __tablename__ = "holiday_calendars"
    __table_args__ = (
        Index("ix_holiday_org_scope", "organization_id", "scope"),
        Index("ix_holiday_date", "organization_id", "holiday_date"),
    )

    scope: Mapped[HolidayScope] = mapped_column(
        String(32), default=HolidayScope.ORGANIZATION, index=True
    )
    scope_id: Mapped[str | None] = mapped_column(String(255), default=None)
    """A region/country code for ``REGIONAL``, an opaque external id for
    ``CUSTOM``; ``None`` for ``GLOBAL`` and ``ORGANIZATION``."""

    name: Mapped[str] = mapped_column(String(255))
    description: Mapped[str | None] = mapped_column(Text, default=None)
    holiday_date: Mapped[date] = mapped_column(Date, index=True)

    is_recurring: Mapped[bool] = mapped_column(Boolean, default=True)
    """When ``True``, this date's month and day repeat every year --
    ``holiday_date``'s own year is a reference year only. When
    ``False``, this row is a one-off exception for its exact year, the
    "Holiday Exceptions" docs/054 names -- an organization observing a
    holiday on a shifted date for one year only, without redefining the
    recurring rule itself."""


__all__ = ["HolidayCalendarEntry"]
