"""``alert_maintenance_windows`` table -- one maintenance window
("MAINTENANCE WINDOWS" "Support"). ``recurrence_rule`` is nullable and
only meaningful for ``window_type=RECURRING`` (an RFC 5545-style
recurrence string, interpreted by
:mod:`app.suppression.maintenance` rather than this model).
"""

from __future__ import annotations

from datetime import datetime

from shared_core.database.base import BaseModel
from sqlalchemy import Boolean, DateTime, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.enums import MaintenanceWindowScope, MaintenanceWindowType


class AlertMaintenanceWindow(BaseModel):
    """One maintenance window."""

    __tablename__ = "alert_maintenance_windows"

    name: Mapped[str] = mapped_column(String(255), index=True)
    window_type: Mapped[MaintenanceWindowType] = mapped_column(String(16), index=True)
    scope: Mapped[MaintenanceWindowScope] = mapped_column(String(16), index=True)
    scope_reference: Mapped[str | None] = mapped_column(String(255), default=None)
    recurrence_rule: Mapped[str | None] = mapped_column(Text, default=None)
    starts_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    ends_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)


__all__ = ["AlertMaintenanceWindow"]
