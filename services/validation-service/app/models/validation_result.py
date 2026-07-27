"""``validation_results`` table -- the outcome of one check against one
target within one execution. ``rule_id`` is nullable because a check
with no matching rule (or no rules defined at all) still produces a
result, just with ``status`` left at
:attr:`~app.models.enums.ValidationResultStatus.UNKNOWN` -- an absent
rule is never silently treated as a pass. ``check_type`` is
denormalized directly onto this row at write time rather than joined
through ``check_id`` on every read, the same
``WorkflowExecutionStep.node_type`` precedent
``services/workflow-runtime-service`` already established for an
identical "this row's own type never changes after it's written"
shape.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from shared_core.database.base import BaseModel
from sqlalchemy import DateTime, Float, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.enums import ValidationCheckType, ValidationResultStatus


class ValidationResult(BaseModel):
    """The outcome of one check against one target within one execution."""

    __tablename__ = "validation_results"

    execution_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("validation_executions.id", ondelete="CASCADE"), index=True
    )
    target_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("validation_targets.id", ondelete="CASCADE"), index=True
    )
    check_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("validation_checks.id", ondelete="CASCADE"), index=True
    )
    check_type: Mapped[ValidationCheckType] = mapped_column(String(24))
    rule_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("validation_rules.id", ondelete="SET NULL"), default=None, index=True
    )
    status: Mapped[ValidationResultStatus] = mapped_column(
        String(16), default=ValidationResultStatus.UNKNOWN, index=True
    )
    message: Mapped[str | None] = mapped_column(Text, default=None)
    evaluated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
    duration_ms: Mapped[float | None] = mapped_column(Float, default=None)


__all__ = ["ValidationResult"]
