"""``monitoring_targets`` table -- one thing this service monitors.

``external_id`` is the target's own identity in whichever service
actually owns it (an inventory-service asset UUID, a
workflow-runtime-service instance UUID, ...) -- this service never
duplicates another service's own record, only references it by id and
re-fetches live state through that service's own REST API at
collection time, the same "reference, never duplicate" shape
``services/validation-service``'s own ``ValidationTarget`` already
established.
"""

from __future__ import annotations

from typing import Any

from shared_core.database.base import BaseModel
from sqlalchemy import JSON, String
from sqlalchemy.orm import Mapped, mapped_column

from app.models.enums import MonitoringTargetType


class MonitoringTarget(BaseModel):
    """One thing this service monitors, identified in its own owning service."""

    __tablename__ = "monitoring_targets"

    target_type: Mapped[MonitoringTargetType] = mapped_column(String(24), index=True)
    external_id: Mapped[str] = mapped_column(String(255), index=True)
    name: Mapped[str] = mapped_column(String(255), index=True)
    target_metadata: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)


__all__ = ["MonitoringTarget"]
