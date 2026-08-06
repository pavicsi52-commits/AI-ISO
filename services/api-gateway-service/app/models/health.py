"""``api_health`` -- one backend instance's own latest probed health."""

from __future__ import annotations

import uuid
from datetime import datetime

from shared_core.database.base import BaseModel
from sqlalchemy import DateTime, Float, ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.models.enums import CircuitBreakerState, HealthState


class ApiServiceHealth(BaseModel):
    """``api_health`` -- one service instance's own last-probed health and circuit state."""

    __tablename__ = "api_health"
    __table_args__ = (
        UniqueConstraint(
            "organization_id", "service_id", "instance_url", name="uq_api_health_instance"
        ),
        Index("ix_api_health_org_service", "organization_id", "service_id"),
    )

    service_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("api_services.id", ondelete="CASCADE"), index=True
    )
    instance_url: Mapped[str] = mapped_column(String(512))

    status: Mapped[HealthState] = mapped_column(String(16), default=HealthState.UNKNOWN, index=True)
    latency_ms: Mapped[float | None] = mapped_column(Float, default=None)
    error: Mapped[str | None] = mapped_column(Text, default=None)

    circuit_state: Mapped[CircuitBreakerState] = mapped_column(
        String(16), default=CircuitBreakerState.CLOSED
    )
    consecutive_failures: Mapped[int] = mapped_column(Integer, default=0)

    checked_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)


__all__ = ["ApiServiceHealth"]
