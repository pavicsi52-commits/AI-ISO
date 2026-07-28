"""``report_audit`` table -- the security record of reporting actions."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from shared_core.database.base import BaseModel
from sqlalchemy import JSON, DateTime, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.enums import AuditAction, AuditOutcome


class ReportAudit(BaseModel):
    """One audited reporting action.

    Append-only by convention: nothing in this service updates or
    deletes a row here. ``DENIED`` is a first-class outcome, because an
    attempt to export a report the caller had no right to is exactly
    what an auditor most wants to see.
    """

    __tablename__ = "report_audit"

    action: Mapped[AuditAction] = mapped_column(String(32), index=True)
    outcome: Mapped[AuditOutcome] = mapped_column(
        String(16), default=AuditOutcome.SUCCESS, index=True
    )
    entity_type: Mapped[str] = mapped_column(String(64), index=True)
    entity_id: Mapped[uuid.UUID | None] = mapped_column(default=None, index=True)
    actor_id: Mapped[uuid.UUID | None] = mapped_column(default=None, index=True)
    reason: Mapped[str | None] = mapped_column(Text, default=None)
    context: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)


__all__ = ["ReportAudit"]
