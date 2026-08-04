"""``maintenance_windows`` -- periods that suppress or override job execution."""

from __future__ import annotations

from datetime import datetime

from shared_core.database.base import BaseModel
from sqlalchemy import Boolean, DateTime, Index, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.enums import CalendarRuleKind, MaintenanceWindowKind, MaintenanceWindowScope


class MaintenanceWindow(BaseModel):
    """``maintenance_windows`` -- one window a job's execution is checked against."""

    __tablename__ = "maintenance_windows"
    __table_args__ = (
        Index("ix_maintenance_window_org_scope", "organization_id", "scope"),
        Index("ix_maintenance_window_starts", "organization_id", "starts_at"),
    )

    scope: Mapped[MaintenanceWindowScope] = mapped_column(
        String(32), default=MaintenanceWindowScope.ORGANIZATION, index=True
    )
    scope_id: Mapped[str | None] = mapped_column(String(255), default=None)
    """Opaque external id the window applies to -- a project, environment,
    or asset id, as those platform services define them. ``None`` for
    ``GLOBAL`` and ``ORGANIZATION`` scope, where the scope alone is the
    whole answer."""

    kind: Mapped[MaintenanceWindowKind] = mapped_column(
        String(32), default=MaintenanceWindowKind.STANDARD
    )
    title: Mapped[str] = mapped_column(String(255))
    description: Mapped[str | None] = mapped_column(Text, default=None)

    starts_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    ends_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    timezone: Mapped[str] = mapped_column(String(64), default="UTC")

    recurrence: Mapped[CalendarRuleKind] = mapped_column(String(32), default=CalendarRuleKind.NONE)
    recurrence_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)

    allow_critical_override: Mapped[bool] = mapped_column(Boolean, default=False)
    """Whether a ``CRITICAL``-priority job may still dispatch while this
    window is active -- the "Override Rules" docs/054 names. ``kind`` is
    categorisation for reporting; every active window suppresses
    dispatch uniformly, and this is the one escape hatch, applied the
    same way regardless of ``kind``."""


__all__ = ["MaintenanceWindow"]
