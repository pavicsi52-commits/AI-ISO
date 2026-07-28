"""``alert_audit`` table. Per docs/045 "AUDIT": Rule Changes, Alert
Lifecycle, Escalation, Acknowledgements, Suppression, Maintenance
Changes, Administrative Operations. Class named
``AlertAuditEntry``, not ``AlertAudit``, matching the same "avoid a
bare-noun class name that reads like a verb/table-name collision"
precedent ``services/monitoring-service``'s own
``MonitoringAuditEntry`` established.

Distinct from :class:`~app.models.alert_history.AlertHistory`: that is
one alert's own status timeline (a per-alert read), this is the
organization-wide record of privileged/administrative actions against
alerting *configuration*.
"""

from __future__ import annotations

import uuid
from typing import Any

from shared_core.database.base import BaseModel
from sqlalchemy import JSON, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.enums import AuditOutcome


class AlertAuditEntry(BaseModel):
    """One privileged/administrative action recorded against alerting configuration."""

    __tablename__ = "alert_audit"

    actor_id: Mapped[uuid.UUID | None] = mapped_column(default=None)
    action: Mapped[str] = mapped_column(String(64))
    entity_type: Mapped[str] = mapped_column(String(64))
    entity_id: Mapped[uuid.UUID | None] = mapped_column(default=None)
    outcome: Mapped[AuditOutcome] = mapped_column(String(16), default=AuditOutcome.SUCCESS)
    reason: Mapped[str] = mapped_column(Text, default="")
    details: Mapped[dict[str, Any] | None] = mapped_column(JSON, default=None)


__all__ = ["AlertAuditEntry"]
