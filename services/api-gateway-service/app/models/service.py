"""``api_services`` -- one backend service the gateway can route to.

Per docs/056 "LOAD BALANCING", one logical service may have several
live backend instances; rather than a sixteenth table this schema does
not have room for under the prompt's own literal fifteen-table list,
:attr:`ApiService.instances` holds them as a JSON list of
``{"url": ..., "weight": ...}`` objects -- exactly the shape
:mod:`app.loadbalancing.engine` already needs to choose between them.
"""

from __future__ import annotations

from typing import Any

from shared_core.database.base import BaseModel
from sqlalchemy import JSON, Boolean, Float, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.enums import LoadBalancingStrategy


class ApiService(BaseModel):
    """``api_services`` -- one backend service registered behind the gateway."""

    __tablename__ = "api_services"

    name: Mapped[str] = mapped_column(String(128), index=True)
    description: Mapped[str | None] = mapped_column(Text, default=None)

    instances: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)
    """Every live backend instance: ``[{"url": "http://host:port", "weight": 100}, ...]``."""

    load_balancing_strategy: Mapped[LoadBalancingStrategy] = mapped_column(
        String(32), default=LoadBalancingStrategy.ROUND_ROBIN
    )
    health_check_path: Mapped[str] = mapped_column(String(255), default="/health")
    timeout_seconds: Mapped[float | None] = mapped_column(Float, default=None)
    circuit_breaker_enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)


__all__ = ["ApiService"]
