"""``validation_rules`` table -- the pass/fail/warn logic evaluated
against one :class:`~app.models.validation_check.ValidationCheck`'s own
collected data ("Rule Chaining"/"Conditional Checks"). ``condition`` is
a Jinja2-sandboxed boolean expression (reusing
``shared_core.workflow.expressions.evaluate_condition``, the same
proven-safe evaluator ``shared_core.workflow``'s own conditional nodes
already use, rather than a hand-rolled or ``eval``-based one) evaluated
against the check's own collected data dict, e.g.
``"disk_usage_percent > 90"``. Multiple rules may reference the same
check at different thresholds (e.g. one ``WARNING``-severity rule at
80%, one ``CRITICAL``-severity rule at 95%); ``priority`` orders
evaluation within a check the same way
``shared_core.workflow.conditions.evaluate_rules`` orders an ordered
rule chain, first match (by ``priority``, ascending) wins.
"""

from __future__ import annotations

import uuid

from shared_core.database.base import BaseModel
from sqlalchemy import Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.enums import ValidationResultStatus, ValidationSeverity


class ValidationRule(BaseModel):
    """The pass/fail/warn logic evaluated against one check's own collected data."""

    __tablename__ = "validation_rules"

    check_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("validation_checks.id", ondelete="CASCADE"), index=True
    )
    name: Mapped[str] = mapped_column(String(255), index=True)
    description: Mapped[str | None] = mapped_column(Text, default=None)
    condition: Mapped[str] = mapped_column(Text)
    result_status: Mapped[ValidationResultStatus] = mapped_column(
        String(16), default=ValidationResultStatus.FAILED
    )
    severity: Mapped[ValidationSeverity] = mapped_column(
        String(16), default=ValidationSeverity.MEDIUM
    )
    weight: Mapped[float] = mapped_column(Float, default=1.0)
    remediation_hint: Mapped[str | None] = mapped_column(Text, default=None)
    priority: Mapped[int] = mapped_column(Integer, default=0)


__all__ = ["ValidationRule"]
