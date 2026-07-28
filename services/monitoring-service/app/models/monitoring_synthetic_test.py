"""``monitoring_synthetic_tests`` table -- a standalone, scheduled
synthetic check configuration ("SYNTHETIC MONITORING" "Support").
``target_id`` is nullable -- a synthetic test may probe a registered
target (e.g. "is this known server's own API reachable") or a bare
external endpoint with no corresponding
:class:`~app.models.monitoring_target.MonitoringTarget` row at all
(e.g. a third-party dependency this service doesn't otherwise track).
No separate results table exists in docs/044's own 17-table list --
each run's own outcome is persisted into
:class:`~app.models.monitoring_metric_series.MonitoringMetricSeries`
(e.g. ``"synthetic_response_time_ms"``) and
:class:`~app.models.monitoring_health.MonitoringHealth`
(pass/fail as a health status), reusing the same tables every other
collector already writes into rather than inventing an eighteenth.
"""

from __future__ import annotations

import uuid
from typing import Any

from shared_core.database.base import BaseModel
from sqlalchemy import JSON, Boolean, Float, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from app.models.enums import SyntheticCheckType


class MonitoringSyntheticTest(BaseModel):
    """A standalone, scheduled synthetic check configuration."""

    __tablename__ = "monitoring_synthetic_tests"

    target_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("monitoring_targets.id", ondelete="SET NULL"), default=None, index=True
    )
    check_type: Mapped[SyntheticCheckType] = mapped_column(String(16), index=True)
    name: Mapped[str] = mapped_column(String(255), index=True)
    parameters: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    interval_seconds: Mapped[float] = mapped_column(Float, default=300.0)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)


__all__ = ["MonitoringSyntheticTest"]
