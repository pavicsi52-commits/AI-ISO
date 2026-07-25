"""``configuration_drift`` table. Per docs/039 "DRIFT DETECTION"
"Detect": Missing Configuration, Unexpected Changes, Unauthorized
Changes, Version Drift, Policy Drift, Template Drift, Variable Drift,
"Schedule Periodic Drift Analysis".
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from shared_core.database.base import BaseModel
from sqlalchemy import JSON, DateTime, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from app.models.enums import DriftStatus, DriftType


class ConfigurationDrift(BaseModel):
    """One detected drift instance between desired and actual state."""

    __tablename__ = "configuration_drift"

    profile_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("configuration_profiles.id", ondelete="CASCADE"), nullable=False, index=True
    )
    managed_asset_id: Mapped[uuid.UUID] = mapped_column(nullable=False, index=True)
    drift_type: Mapped[DriftType] = mapped_column(String(32), index=True)
    status: Mapped[DriftStatus] = mapped_column(
        String(16), default=DriftStatus.DETECTED, index=True
    )
    detected_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    details: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
    resolved_by: Mapped[uuid.UUID | None] = mapped_column(default=None)


__all__ = ["ConfigurationDrift"]
