"""``alert_conditions`` table -- one expression evaluated as part of a
:class:`~app.models.alert_rule.AlertRule`'s own boolean-combined
condition set ("Composite Rules"/"Boolean Logic"/"Pattern Matching"/
"Custom Expressions"). ``sequence`` orders conditions for display and
short-circuit evaluation; ``expression`` is a Jinja2-sandboxed boolean
expression, the same evaluator every prior AI-IOS rule engine already
established.
"""

from __future__ import annotations

import uuid

from shared_core.database.base import BaseModel
from sqlalchemy import ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column


class AlertCondition(BaseModel):
    """One expression evaluated as part of a rule's own condition set."""

    __tablename__ = "alert_conditions"

    rule_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("alert_rules.id", ondelete="CASCADE"), index=True
    )
    sequence: Mapped[int] = mapped_column(Integer, default=0)
    metric_name: Mapped[str | None] = mapped_column(String(255), default=None)
    expression: Mapped[str] = mapped_column(Text)


__all__ = ["AlertCondition"]
