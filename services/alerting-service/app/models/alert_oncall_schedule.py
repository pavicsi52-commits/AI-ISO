"""``alert_oncall_schedules`` table -- one on-call rotation schedule
("ON-CALL MANAGEMENT" "Support": Schedules, Rotations, Time Zones,
Overrides, Holiday Calendars). ``participants`` is an ordered JSON list
of user ids the rotation cycles through; ``overrides`` is a JSON list
of ``{"user_id": ..., "starts_at": ..., "ends_at": ...}`` objects
temporarily replacing the computed rotation slot ("Overrides").
"""

from __future__ import annotations

from typing import Any

from shared_core.database.base import BaseModel
from sqlalchemy import JSON, Boolean, String
from sqlalchemy.orm import Mapped, mapped_column

from app.models.enums import OnCallRotationType


class AlertOnCallSchedule(BaseModel):
    """One on-call rotation schedule."""

    __tablename__ = "alert_oncall_schedules"

    name: Mapped[str] = mapped_column(String(255), index=True)
    rotation_type: Mapped[OnCallRotationType] = mapped_column(String(16), index=True)
    timezone: Mapped[str] = mapped_column(String(64), default="UTC")
    participants: Mapped[list[str]] = mapped_column(JSON, default=list)
    overrides: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)
    holiday_calendar: Mapped[list[str]] = mapped_column(JSON, default=list)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)


__all__ = ["AlertOnCallSchedule"]
