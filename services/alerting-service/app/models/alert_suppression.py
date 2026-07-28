"""``alert_suppression`` table -- one active or scheduled suppression
window ("SUPPRESSION" "Support"). ``scope_reference`` names whatever
the suppression applies to (an asset id, a rule id, a dependency chain
root, etc.) generically, matching
:class:`~app.models.alert_instance.AlertInstance`'s own
``source_reference`` "identify by string, not a typed foreign key into
every possible target" shape, since a suppression may scope to
anything ("Maintenance Windows"/"Dependency Suppression"/"Parent/Child
Suppression").
"""

from __future__ import annotations

from datetime import datetime

from shared_core.database.base import BaseModel
from sqlalchemy import Boolean, DateTime, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.enums import SuppressionType


class AlertSuppression(BaseModel):
    """One active or scheduled suppression window.

    ``created_by`` (who requested it) is inherited from
    ``BaseEntityMixin``, not redefined here.
    """

    __tablename__ = "alert_suppression"

    suppression_type: Mapped[SuppressionType] = mapped_column(String(24), index=True)
    scope_reference: Mapped[str | None] = mapped_column(String(255), default=None)
    reason: Mapped[str | None] = mapped_column(Text, default=None)
    starts_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    ends_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)


__all__ = ["AlertSuppression"]
