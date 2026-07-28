"""``monitoring_rules`` table -- the rule engine's own condition catalog
("RULE ENGINE" "Support"). ``condition`` is a Jinja2-sandboxed boolean
expression (reusing ``shared_core.workflow.expressions
.evaluate_condition``, the same proven-safe evaluator
``services/validation-service``'s own rule engine already established,
rather than a hand-rolled or ``eval()``-based one) evaluated against
the metric's own recent collected data. ``window_seconds`` backs
"Window Aggregation" (evaluate against an aggregate over a rolling
window, not a single point); ``escalation_after_seconds`` backs
"Escalation Triggers" (only fire after the condition has held
continuously for this long).
"""

from __future__ import annotations

import uuid

from shared_core.database.base import BaseModel
from shared_core.monitoring.thresholds import ThresholdLevel
from sqlalchemy import Boolean, Float, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.enums import MonitoringRuleType


class MonitoringRule(BaseModel):
    """One rule engine condition against a metric's own collected data."""

    __tablename__ = "monitoring_rules"

    metric_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("monitoring_metrics.id", ondelete="CASCADE"), default=None, index=True
    )
    rule_type: Mapped[MonitoringRuleType] = mapped_column(String(16), index=True)
    name: Mapped[str] = mapped_column(String(255), index=True)
    description: Mapped[str | None] = mapped_column(Text, default=None)
    condition: Mapped[str] = mapped_column(Text)
    severity: Mapped[ThresholdLevel] = mapped_column(String(16), default=ThresholdLevel.MEDIUM)
    window_seconds: Mapped[float | None] = mapped_column(Float, default=None)
    escalation_after_seconds: Mapped[float | None] = mapped_column(Float, default=None)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)


__all__ = ["MonitoringRule"]
