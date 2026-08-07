"""``plugin_health``."""

from __future__ import annotations

import uuid
from datetime import datetime

from shared_core.database.base import BaseModel
from shared_core.enums.health_status import HealthStatus
from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column


class PluginHealth(BaseModel):
    """``plugin_health`` -- one automated health-probe result for an
    installed plugin instance.

    ``status`` reuses ``shared_core.enums.health_status.HealthStatus``
    directly, matching ``integration-hub-service``'s own
    ``ConnectorHealth`` (Prompt 058) -- this platform's established
    health vocabulary.
    """

    __tablename__ = "plugin_health"
    __table_args__ = (Index("ix_plugin_health_installation", "plugin_installation_id"),)

    plugin_installation_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("plugin_installations.id", ondelete="CASCADE"), index=True
    )
    status: Mapped[HealthStatus] = mapped_column(
        String(16), default=HealthStatus.UNKNOWN, index=True
    )
    latency_ms: Mapped[float | None] = mapped_column(Float, default=None)
    checked_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    error: Mapped[str | None] = mapped_column(Text, default=None)
    consecutive_failures: Mapped[int] = mapped_column(Integer, default=0)
    recovery_attempted: Mapped[bool] = mapped_column(Boolean, default=False)


__all__ = ["PluginHealth"]
