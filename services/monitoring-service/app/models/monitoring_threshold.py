"""``monitoring_thresholds`` table -- a persisted, organization-scoped
threshold configuration for a metric. Mirrors
:class:`shared_core.monitoring.thresholds.Threshold`'s own five
breach-level fields exactly (``informational``/``low``/``medium``/
``high``/``critical``, any subset of which may be set) so a row here
can be converted directly into that dataclass at evaluation time via
:func:`app.rules.thresholds.to_shared_threshold` rather than
duplicating its own ``evaluate()`` breach logic.
"""

from __future__ import annotations

import uuid

from shared_core.database.base import BaseModel
from sqlalchemy import Boolean, Float, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from app.models.enums import ThresholdType


class MonitoringThreshold(BaseModel):
    """A persisted threshold configuration for a metric."""

    __tablename__ = "monitoring_thresholds"

    metric_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("monitoring_metrics.id", ondelete="CASCADE"), index=True
    )
    threshold_type: Mapped[ThresholdType] = mapped_column(String(16), default=ThresholdType.STATIC)
    informational: Mapped[float | None] = mapped_column(Float, default=None)
    low: Mapped[float | None] = mapped_column(Float, default=None)
    medium: Mapped[float | None] = mapped_column(Float, default=None)
    high: Mapped[float | None] = mapped_column(Float, default=None)
    critical: Mapped[float | None] = mapped_column(Float, default=None)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)


__all__ = ["MonitoringThreshold"]
