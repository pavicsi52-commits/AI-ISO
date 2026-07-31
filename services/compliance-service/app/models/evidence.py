"""``compliance_evidence``, ``compliance_findings``, ``compliance_exceptions``.

Proof, what the proof showed was wrong, and what was consciously
tolerated anyway.

**Evidence is immutable** (docs/051, "SECURITY: Immutable evidence").
That is enforced here rather than left to convention: every row is
content-hashed at creation, the hash is verifiable afterwards, and the
repository refuses updates. The reason is narrow and important --
evidence exists to be shown to somebody who does not trust you. Evidence
that could have been edited after the fact proves only that a row
existed, and an auditor who finds one editable row has to discard the
whole trail rather than just that one.

Superseding, not editing, is how corrected evidence works: the new row
points at the old one and both survive.
"""

from __future__ import annotations

import hashlib
import json
import uuid
from datetime import datetime
from typing import Any

from shared_core.database.base import BaseModel
from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.models.enums import (
    EvidenceKind,
    EvidenceSource,
    ExceptionKind,
    ExceptionStatus,
    FindingSeverity,
    FindingStatus,
)


def content_digest(payload: dict[str, Any]) -> str:
    """The SHA-256 of a canonical rendering of *payload*.

    ``sort_keys`` and a fixed separator make the digest independent of
    dictionary ordering, so the same evidence hashes the same way on
    every machine and in every Python version. Without that, verification
    would fail for reasons that have nothing to do with tampering --
    which trains people to ignore verification failures, the one outcome
    worse than not verifying at all.
    """
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


class ComplianceEvidence(BaseModel):
    """``compliance_evidence`` -- one immutable piece of proof."""

    __tablename__ = "compliance_evidence"
    __table_args__ = (
        Index("ix_compliance_evidence_org", "organization_id", "collected_at"),
        Index("ix_compliance_evidence_control", "organization_id", "control_id"),
        Index("ix_compliance_evidence_assessment", "organization_id", "assessment_id"),
        Index("ix_compliance_evidence_digest", "organization_id", "digest"),
    )

    assessment_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("compliance_assessments.id", ondelete="SET NULL"), default=None, index=True
    )
    control_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("compliance_controls.id", ondelete="SET NULL"), default=None, index=True
    )

    kind: Mapped[EvidenceKind] = mapped_column(String(64), index=True)
    source: Mapped[EvidenceSource] = mapped_column(String(64), index=True)
    source_reference: Mapped[str | None] = mapped_column(String(512), default=None)
    """Where in the source system this came from -- a job id, a metric
    query, a document name. What makes the evidence checkable rather
    than merely present."""

    title: Mapped[str] = mapped_column(String(512))
    description: Mapped[str | None] = mapped_column(Text, default=None)

    target_type: Mapped[str | None] = mapped_column(String(64), default=None)
    target_id: Mapped[str | None] = mapped_column(String(255), default=None, index=True)

    payload: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    digest: Mapped[str] = mapped_column(String(64), index=True)
    """SHA-256 of :attr:`payload`, computed once at creation.

    Verification recomputes it and compares. A mismatch means the row was
    changed by something that bypassed this service -- direct SQL, a
    restore from a doctored backup -- which is exactly the case a stored
    checksum is for, and exactly the case an application-level "immutable"
    flag would miss."""

    collected_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    collected_by: Mapped[str | None] = mapped_column(String(255), default=None)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
    """When this proof stops being current. A configuration snapshot from
    eighteen months ago does not show today's estate, and an audit
    package built from stale evidence fails in the room."""

    supersedes_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("compliance_evidence.id", ondelete="SET NULL"), default=None
    )
    """Correction is by supersession, never by edit. Both rows survive,
    and the chain shows what was believed and when."""

    is_superseded: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    size_bytes: Mapped[int] = mapped_column(Integer, default=0)
    content_type: Mapped[str | None] = mapped_column(String(128), default=None)
    storage_key: Mapped[str | None] = mapped_column(String(1_024), default=None)
    tags: Mapped[list[str]] = mapped_column(JSON, default=list)
    attributes: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)


class ComplianceFinding(BaseModel):
    """``compliance_findings`` -- a control that is not being met."""

    __tablename__ = "compliance_findings"
    __table_args__ = (
        Index("ix_compliance_finding_org", "organization_id", "status", "severity"),
        Index("ix_compliance_finding_control", "organization_id", "control_id"),
        Index("ix_compliance_finding_assignee", "organization_id", "assignee_id"),
        Index("ix_compliance_finding_fingerprint", "organization_id", "fingerprint"),
    )

    assessment_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("compliance_assessments.id", ondelete="SET NULL"), default=None, index=True
    )
    result_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("compliance_results.id", ondelete="SET NULL"), default=None
    )
    control_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("compliance_controls.id", ondelete="CASCADE"), index=True
    )
    framework_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("compliance_frameworks.id", ondelete="SET NULL"), default=None, index=True
    )

    title: Mapped[str] = mapped_column(String(512))
    description: Mapped[str | None] = mapped_column(Text, default=None)
    severity: Mapped[FindingSeverity] = mapped_column(
        String(32), default=FindingSeverity.MEDIUM, index=True
    )
    status: Mapped[FindingStatus] = mapped_column(
        String(32), default=FindingStatus.OPEN, index=True
    )

    fingerprint: Mapped[str] = mapped_column(String(64), index=True)
    """Stable identity for "this same problem, on this same thing".

    A daily assessment must not raise 365 findings for one unpatched
    host. The fingerprint is what lets a re-detection update the existing
    finding -- preserving its assignee, its comments, and its age -- and
    the age is the number that makes an overdue finding visible at all.
    """

    target_type: Mapped[str | None] = mapped_column(String(64), default=None)
    target_id: Mapped[str | None] = mapped_column(String(255), default=None, index=True)
    target_name: Mapped[str | None] = mapped_column(String(512), default=None)

    risk_score: Mapped[float] = mapped_column(Float, default=0.0)
    assignee_id: Mapped[str | None] = mapped_column(String(255), default=None)
    assigned_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
    due_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)

    first_detected_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    last_detected_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    detection_count: Mapped[int] = mapped_column(Integer, default=1)

    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
    resolved_by: Mapped[str | None] = mapped_column(String(255), default=None)
    resolution_note: Mapped[str | None] = mapped_column(Text, default=None)

    evidence_ids: Mapped[list[str]] = mapped_column(JSON, default=list)
    exception_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("compliance_exceptions.id", ondelete="SET NULL"), default=None
    )
    risk_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("compliance_risk_register.id", ondelete="SET NULL"), default=None
    )
    tags: Mapped[list[str]] = mapped_column(JSON, default=list)
    attributes: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)


class ComplianceException(BaseModel):
    """``compliance_exceptions`` -- a control consciously not met."""

    __tablename__ = "compliance_exceptions"
    __table_args__ = (
        Index("ix_compliance_exception_org", "organization_id", "status"),
        Index("ix_compliance_exception_control", "organization_id", "control_id"),
        Index("ix_compliance_exception_expiry", "organization_id", "expires_at"),
        Index("ix_compliance_exception_review", "organization_id", "next_review_at"),
    )

    control_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("compliance_controls.id", ondelete="CASCADE"), index=True
    )
    framework_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("compliance_frameworks.id", ondelete="SET NULL"), default=None
    )
    # There is deliberately no ``finding_id`` here.
    #
    # One exception waives *many* findings -- the same unpatched control
    # across forty hosts is forty findings and one waiver -- so the
    # relationship belongs on the many side, as
    # :attr:`ComplianceFinding.exception_id`. A column here could only
    # ever name one of them, which reads as "the finding this was granted
    # for" and then disagrees with the other thirty-nine. It also closed
    # a foreign-key cycle that no ordering of ``CREATE TABLE`` can
    # satisfy, which is how the redundancy announced itself.

    title: Mapped[str] = mapped_column(String(512))
    kind: Mapped[ExceptionKind] = mapped_column(String(32), default=ExceptionKind.TEMPORARY)
    status: Mapped[ExceptionStatus] = mapped_column(
        String(32), default=ExceptionStatus.REQUESTED, index=True
    )

    business_justification: Mapped[str] = mapped_column(Text)
    """Mandatory. An exception without a stated reason is indistinguishable
    from an oversight, and the whole value of an exception register is
    that somebody can later ask whether the reason still holds."""

    risk_acceptance: Mapped[str | None] = mapped_column(Text, default=None)
    compensating_control: Mapped[str | None] = mapped_column(Text, default=None)

    target_type: Mapped[str | None] = mapped_column(String(64), default=None)
    target_id: Mapped[str | None] = mapped_column(String(255), default=None, index=True)

    requested_by: Mapped[str | None] = mapped_column(String(255), default=None)
    requested_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
    approved_by: Mapped[str | None] = mapped_column(String(255), default=None)
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
    rejected_reason: Mapped[str | None] = mapped_column(Text, default=None)

    effective_from: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
    expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), default=None, index=True
    )
    """Null only for a ``PERMANENT`` exception, which still carries a
    mandatory :attr:`next_review_at` -- a waiver nobody ever looks at
    again is an undocumented policy change, whatever it is called."""

    next_review_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), default=None, index=True
    )
    review_interval_days: Mapped[int] = mapped_column(Integer, default=90)
    last_reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
    last_reviewed_by: Mapped[str | None] = mapped_column(String(255), default=None)

    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
    revoked_by: Mapped[str | None] = mapped_column(String(255), default=None)
    revocation_reason: Mapped[str | None] = mapped_column(Text, default=None)

    use_count: Mapped[int] = mapped_column(Integer, default=0)
    """How many results this waiver has excused. A number nobody looks at
    until it is large, at which point it is the clearest evidence that a
    "temporary" exception has become the actual policy."""

    last_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
    attributes: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)


__all__ = [
    "ComplianceEvidence",
    "ComplianceException",
    "ComplianceFinding",
    "content_digest",
]
