"""``alert_escalation`` table -- one escalation policy ("ESCALATION"
"Support": Escalation Policies, Time-based Escalation, Multi-level
Escalation). ``levels`` is a JSON list of
``{"target_type": ..., "target_reference": ..., "delay_seconds": ...}``
objects, evaluated in order -- no separate "escalation levels" table
exists in docs/045's own 16-table list, so a policy's own ordered
level chain is stored inline rather than normalized into an
eighteenth-table-equivalent this schema was never asked for.
"""

from __future__ import annotations

from typing import Any

from shared_core.database.base import BaseModel
from sqlalchemy import JSON, Boolean, String
from sqlalchemy.orm import Mapped, mapped_column


class AlertEscalationPolicy(BaseModel):
    """One escalation policy, with an ordered chain of levels."""

    __tablename__ = "alert_escalation"

    name: Mapped[str] = mapped_column(String(255), index=True)
    levels: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)


__all__ = ["AlertEscalationPolicy"]
