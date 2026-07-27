"""``validation_scores`` table -- the weighted scoring rollup for one
execution. Per docs/043's own "SCORING" "Generate" list, verbatim: one
float column per named score category plus the overall score, computed
by :mod:`app.scoring.engine` from that execution's own
:class:`~app.models.validation_result.ValidationResult` rows weighted
by each result's own :class:`~app.models.validation_rule.ValidationRule
.weight`. A category score is ``None`` when the execution's own checks
never touched that category at all (e.g. a purely "Health Profile" run
has no meaningful security score), rather than defaulting to a
misleading ``0.0`` or ``100.0``.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from shared_core.database.base import BaseModel
from sqlalchemy import DateTime, Float, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column


class ValidationScore(BaseModel):
    """The weighted scoring rollup for one execution."""

    __tablename__ = "validation_scores"

    execution_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("validation_executions.id", ondelete="CASCADE"), index=True
    )
    overall_score: Mapped[float] = mapped_column(Float, default=0.0)
    infrastructure_score: Mapped[float | None] = mapped_column(Float, default=None)
    security_score: Mapped[float | None] = mapped_column(Float, default=None)
    compliance_score: Mapped[float | None] = mapped_column(Float, default=None)
    configuration_score: Mapped[float | None] = mapped_column(Float, default=None)
    performance_score: Mapped[float | None] = mapped_column(Float, default=None)
    health_score: Mapped[float | None] = mapped_column(Float, default=None)
    computed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)


__all__ = ["ValidationScore"]
