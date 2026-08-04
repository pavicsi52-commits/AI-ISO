"""``incident_root_causes``, ``problem_records``, ``known_errors``.

Why it happened, the recurring pattern it might be part of, and the
understood-but-unfixed condition that pattern turns into.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from shared_core.database.base import BaseModel
from sqlalchemy import (
    JSON,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.models.enums import ProblemStatus, RcaMethod


class IncidentRootCause(BaseModel):
    """``incident_root_causes`` -- why an incident happened.

    One row per finding, not one mutable field on the incident: root
    cause understanding evolves as an investigation proceeds, and the
    sequence -- what was believed first, what replaced it -- is itself
    evidence for the postmortem's "why did this take so long to
    diagnose" section.
    """

    __tablename__ = "incident_root_causes"
    __table_args__ = (
        Index("ix_root_cause_incident", "organization_id", "incident_id", "recorded_at"),
    )

    incident_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("incidents.id", ondelete="CASCADE"), index=True
    )
    method: Mapped[RcaMethod] = mapped_column(String(32), default=RcaMethod.MANUAL, index=True)
    summary: Mapped[str] = mapped_column(Text)
    contributing_factors: Mapped[list[str]] = mapped_column(JSON, default=list)
    confidence: Mapped[float] = mapped_column(Float, default=1.0)
    """How sure this finding is, 0.0-1.0. An AI-assisted or
    alert-correlation finding is a hypothesis until a person confirms
    it; a manual finding recorded by the investigating engineer is not,
    and treating the two the same way overstates how well an incident
    was actually understood."""

    is_confirmed: Mapped[bool] = mapped_column(default=False)
    confirmed_by: Mapped[str | None] = mapped_column(String(255), default=None)
    evidence: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    """Correlated alert ids, graph traversal results, validation run
    ids, configuration drift diffs -- whatever backs this finding, kept
    as references rather than duplicated data."""

    recorded_by: Mapped[str | None] = mapped_column(String(255), default=None)
    recorded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)


class ProblemRecord(BaseModel):
    """``problem_records`` -- a recurring pattern across incidents."""

    __tablename__ = "problem_records"
    __table_args__ = (
        UniqueConstraint("organization_id", "reference", name="uq_problem_reference"),
        Index("ix_problem_org_status", "organization_id", "status"),
    )

    reference: Mapped[str] = mapped_column(String(64))
    title: Mapped[str] = mapped_column(String(512))
    description: Mapped[str | None] = mapped_column(Text, default=None)
    status: Mapped[ProblemStatus] = mapped_column(
        String(32), default=ProblemStatus.OPEN, index=True
    )

    incident_ids: Mapped[list[str]] = mapped_column(JSON, default=list)
    incident_count: Mapped[int] = mapped_column(Integer, default=0)
    """Denormalised from :attr:`incident_ids`' length, recounted rather
    than incremented -- see ``IncidentRepository.refresh_incident_count``
    -- so a problem's own denominator cannot drift from the incidents
    that actually cite it."""

    owner_id: Mapped[str | None] = mapped_column(String(255), default=None)
    permanent_fix: Mapped[str | None] = mapped_column(Text, default=None)
    permanent_fix_status: Mapped[str | None] = mapped_column(String(64), default=None)

    identified_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)

    tags: Mapped[list[str]] = mapped_column(JSON, default=list)
    attributes: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)


class KnownError(BaseModel):
    """``known_errors`` -- an understood problem with no permanent fix yet.

    Separate from :class:`ProblemRecord` even though every known error
    has exactly one problem behind it, because a known error is read by
    a different audience under time pressure: the person triaging a new
    incident at 03:00 who needs "is this already understood, and if so
    what is the workaround" in one lookup, not the fix-tracking detail a
    problem owner needs.
    """

    __tablename__ = "known_errors"
    __table_args__ = (Index("ix_known_error_problem", "organization_id", "problem_id"),)

    problem_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("problem_records.id", ondelete="CASCADE"), index=True
    )
    title: Mapped[str] = mapped_column(String(512))
    root_cause_summary: Mapped[str] = mapped_column(Text)
    workaround: Mapped[str | None] = mapped_column(Text, default=None)
    """What to do *right now*, before the permanent fix ships. The
    field the 03:00 lookup is actually for."""

    affected_versions: Mapped[list[str]] = mapped_column(JSON, default=list)
    is_active: Mapped[bool] = mapped_column(default=True, index=True)
    recorded_by: Mapped[str | None] = mapped_column(String(255), default=None)
    recorded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    retired_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)


__all__ = ["IncidentRootCause", "KnownError", "ProblemRecord"]
