"""``monitoring_collectors`` table -- a reusable, standalone
configuration for one distributed collector ("Distributed Collectors").
``collector_key`` names which function in ``app/collectors/`` gathers
the raw data (e.g. ``"cpu_usage"``); ``target_types`` scopes which
kinds of target this collector applies to. A collector only *collects*
-- whether a collected value breaches a threshold is a separate
concern, evaluated by :class:`~app.models.monitoring_threshold
.MonitoringThreshold`/:class:`~app.models.monitoring_rule.MonitoringRule`.
"""

from __future__ import annotations

from typing import Any

from shared_core.database.base import BaseModel
from sqlalchemy import JSON, Boolean, Float, String
from sqlalchemy.orm import Mapped, mapped_column


class MonitoringCollector(BaseModel):
    """A reusable, standalone configuration for one distributed collector."""

    __tablename__ = "monitoring_collectors"

    name: Mapped[str] = mapped_column(String(255), index=True)
    collector_key: Mapped[str] = mapped_column(String(64), index=True)
    target_types: Mapped[list[str]] = mapped_column(JSON, default=list)
    parameters: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    interval_seconds: Mapped[float] = mapped_column(Float, default=60.0)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)


__all__ = ["MonitoringCollector"]
