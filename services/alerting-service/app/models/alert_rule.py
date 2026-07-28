"""``alert_rules`` table -- the rule engine's own top-level rule
definition ("RULE ENGINE" "Support"). One or more
:class:`~app.models.alert_condition.AlertCondition` rows attach to a
rule and combine via ``boolean_operator`` ("Composite Rules"/"Boolean
Logic"); ``rule_type``/``window_seconds`` back "Time Window Rules"/
"Rate of Change". Named ``enabled``, not ``is_active``, since the
inherited ``BaseEntityMixin.is_active`` is a soft-delete flag -- a
disabled-but-not-deleted rule is a distinct, real state.
"""

from __future__ import annotations

from shared_core.database.base import BaseModel
from shared_core.enums.severity import Severity
from sqlalchemy import JSON, Boolean, Float, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.enums import AlertRuleType, AlertSource, BooleanOperator


class AlertRule(BaseModel):
    """One rule engine definition."""

    __tablename__ = "alert_rules"

    name: Mapped[str] = mapped_column(String(255), index=True)
    description: Mapped[str | None] = mapped_column(Text, default=None)
    rule_type: Mapped[AlertRuleType] = mapped_column(String(24), index=True)
    source: Mapped[AlertSource] = mapped_column(String(32), index=True)
    boolean_operator: Mapped[BooleanOperator] = mapped_column(
        String(8), default=BooleanOperator.AND
    )
    severity: Mapped[Severity] = mapped_column(String(16), default=Severity.MEDIUM)
    window_seconds: Mapped[float | None] = mapped_column(Float, default=None)
    tags: Mapped[dict[str, str]] = mapped_column(JSON, default=dict)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)


__all__ = ["AlertRule"]
