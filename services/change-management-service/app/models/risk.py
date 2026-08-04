"""``change_risk_assessments`` -- why a change is believed to be as risky as it is.

One row per assessment, not one mutable set of fields on the change
itself: understanding evolves as more is known about a change, and the
sequence of assessments is itself evidence for "did we actually
reassess before scheduling" -- the same reasoning Prompt 052 applied to
``IncidentRootCause``.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from shared_core.database.base import BaseModel
from sqlalchemy import DateTime, Float, ForeignKey, Index, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.enums import RiskImpact, RiskLevel, RiskLikelihood


class ChangeRiskAssessment(BaseModel):
    """``change_risk_assessments`` -- one scoring of one change's risk."""

    __tablename__ = "change_risk_assessments"
    __table_args__ = (
        Index("ix_risk_assessment_change", "organization_id", "change_id", "assessed_at"),
    )

    change_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("change_requests.id", ondelete="CASCADE"), index=True
    )

    likelihood: Mapped[RiskLikelihood] = mapped_column(String(32))
    impact: Mapped[RiskImpact] = mapped_column(String(32))

    technical_risk: Mapped[RiskImpact] = mapped_column(String(32))
    business_risk: Mapped[RiskImpact] = mapped_column(String(32))
    operational_risk: Mapped[RiskImpact] = mapped_column(String(32))
    security_risk: Mapped[RiskImpact] = mapped_column(String(32))
    compliance_risk: Mapped[RiskImpact] = mapped_column(String(32))
    dependency_risk: Mapped[RiskImpact] = mapped_column(String(32))
    """Six independent dimensions, each scored on the same published
    impact scale, so no single dimension can be quietly averaged away by
    the others -- see ``app/risk/engine.py::composite_risk_level``."""

    automated_score: Mapped[float] = mapped_column(Float)
    risk_level: Mapped[RiskLevel] = mapped_column(String(32), index=True)
    manual_override: Mapped[RiskLevel | None] = mapped_column(String(32), default=None)
    override_reason: Mapped[str | None] = mapped_column(Text, default=None)
    override_by: Mapped[str | None] = mapped_column(String(255), default=None)
    """A human may override the computed banding, but never silently --
    the automated score and the override both survive on the same row,
    so a reviewer sees exactly what was overridden and by how much."""

    approval_recommendation: Mapped[str] = mapped_column(Text)

    assessed_by: Mapped[str | None] = mapped_column(String(255), default=None)
    assessed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)


__all__ = ["ChangeRiskAssessment"]
