"""``compliance_assessments``, ``compliance_scans``, ``compliance_results``.

A run and what it found. An assessment is the unit an auditor asks
about ("show me the Q3 SOC 2 assessment"); a scan is one collector's
pass over one surface; a result is one control's verdict on one target.

**Results are per (control, target), not per control.** A control that
passes on 400 hosts and fails on one is not 99.75% compliant -- it is
failing, and the report has to be able to name the host. Aggregating at
write time would throw away the only fact anyone can act on.
"""

from __future__ import annotations

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
    AssessmentKind,
    AssessmentScope,
    AssessmentStatus,
    ResultStatus,
    ScanKind,
    ScanStatus,
)


class ComplianceAssessment(BaseModel):
    """``compliance_assessments`` -- one evaluation run."""

    __tablename__ = "compliance_assessments"
    __table_args__ = (
        Index("ix_compliance_assessment_org", "organization_id", "started_at"),
        Index("ix_compliance_assessment_status", "organization_id", "status"),
        Index("ix_compliance_assessment_framework", "organization_id", "framework_id"),
    )

    name: Mapped[str] = mapped_column(String(255))
    description: Mapped[str | None] = mapped_column(Text, default=None)
    kind: Mapped[AssessmentKind] = mapped_column(String(32), default=AssessmentKind.ON_DEMAND)
    scope: Mapped[AssessmentScope] = mapped_column(
        String(32), default=AssessmentScope.ORGANIZATION, index=True
    )
    scope_id: Mapped[str | None] = mapped_column(String(255), default=None, index=True)
    status: Mapped[AssessmentStatus] = mapped_column(
        String(32), default=AssessmentStatus.PENDING, index=True
    )

    framework_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("compliance_frameworks.id", ondelete="SET NULL"), default=None, index=True
    )

    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
    duration_ms: Mapped[float | None] = mapped_column(Float, default=None)

    controls_total: Mapped[int] = mapped_column(Integer, default=0)
    controls_passed: Mapped[int] = mapped_column(Integer, default=0)
    controls_failed: Mapped[int] = mapped_column(Integer, default=0)
    controls_warning: Mapped[int] = mapped_column(Integer, default=0)
    controls_not_applicable: Mapped[int] = mapped_column(Integer, default=0)
    controls_not_assessed: Mapped[int] = mapped_column(Integer, default=0)
    controls_errored: Mapped[int] = mapped_column(Integer, default=0)
    controls_excepted: Mapped[int] = mapped_column(Integer, default=0)

    score: Mapped[float | None] = mapped_column(Float, default=None)
    findings_raised: Mapped[int] = mapped_column(Integer, default=0)
    evidence_collected: Mapped[int] = mapped_column(Integer, default=0)

    error: Mapped[str | None] = mapped_column(Text, default=None)
    triggered_by: Mapped[str | None] = mapped_column(String(255), default=None)
    parameters: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    summary: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)


class ComplianceScan(BaseModel):
    """``compliance_scans`` -- one collector's pass over one surface."""

    __tablename__ = "compliance_scans"
    __table_args__ = (
        Index("ix_compliance_scan_org", "organization_id", "started_at"),
        Index("ix_compliance_scan_assessment", "organization_id", "assessment_id"),
        Index("ix_compliance_scan_status", "organization_id", "status"),
    )

    assessment_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("compliance_assessments.id", ondelete="CASCADE"), default=None, index=True
    )
    name: Mapped[str] = mapped_column(String(255))
    kind: Mapped[ScanKind] = mapped_column(String(32), default=ScanKind.COMPLIANCE, index=True)
    status: Mapped[ScanStatus] = mapped_column(String(32), default=ScanStatus.PENDING, index=True)

    target_type: Mapped[str | None] = mapped_column(String(64), default=None)
    target_id: Mapped[str | None] = mapped_column(String(255), default=None, index=True)
    scanner: Mapped[str] = mapped_column(String(128), default="builtin")

    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
    duration_ms: Mapped[float | None] = mapped_column(Float, default=None)

    targets_scanned: Mapped[int] = mapped_column(Integer, default=0)
    checks_run: Mapped[int] = mapped_column(Integer, default=0)
    checks_failed: Mapped[int] = mapped_column(Integer, default=0)
    is_incremental: Mapped[bool] = mapped_column(Boolean, default=False)
    """Whether this pass only looked at what changed since the last one.

    An incremental scan's results are only valid *alongside* the previous
    full scan's, which is why the flag is stored: a score computed from
    incremental results alone would silently cover a fraction of the
    estate while claiming to cover all of it."""

    baseline_scan_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("compliance_scans.id", ondelete="SET NULL"), default=None
    )
    error: Mapped[str | None] = mapped_column(Text, default=None)
    parameters: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    summary: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)


class ComplianceResult(BaseModel):
    """``compliance_results`` -- one control's verdict on one target."""

    __tablename__ = "compliance_results"
    __table_args__ = (
        Index("ix_compliance_result_assessment", "organization_id", "assessment_id"),
        Index("ix_compliance_result_control", "organization_id", "control_id", "status"),
        Index("ix_compliance_result_target", "organization_id", "target_id"),
        Index("ix_compliance_result_evaluated", "organization_id", "evaluated_at"),
    )

    assessment_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("compliance_assessments.id", ondelete="CASCADE"), default=None, index=True
    )
    scan_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("compliance_scans.id", ondelete="SET NULL"), default=None, index=True
    )
    control_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("compliance_controls.id", ondelete="CASCADE"), index=True
    )
    framework_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("compliance_frameworks.id", ondelete="SET NULL"), default=None, index=True
    )

    target_type: Mapped[str | None] = mapped_column(String(64), default=None)
    target_id: Mapped[str | None] = mapped_column(String(255), default=None)
    target_name: Mapped[str | None] = mapped_column(String(512), default=None)

    status: Mapped[ResultStatus] = mapped_column(
        String(32), default=ResultStatus.NOT_ASSESSED, index=True
    )
    reason: Mapped[str | None] = mapped_column(Text, default=None)
    """Why this verdict. Required in practice for every non-``PASS``
    result, because a failure an operator cannot understand is a failure
    nobody fixes."""

    expected: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    observed: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    evaluated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
    duration_ms: Mapped[float | None] = mapped_column(Float, default=None)

    evidence_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("compliance_evidence.id", ondelete="SET NULL"), default=None
    )
    exception_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("compliance_exceptions.id", ondelete="SET NULL"), default=None
    )
    """Set when :attr:`status` is ``EXCEPTED``. A waived failure keeps
    pointing at the waiver that excused it, so "what are we relying on
    exceptions for?" stays an answerable question."""

    error: Mapped[str | None] = mapped_column(Text, default=None)
    attributes: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)


__all__ = ["ComplianceAssessment", "ComplianceResult", "ComplianceScan"]
