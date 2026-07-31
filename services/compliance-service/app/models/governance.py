"""Risk register, remediation, scores, statistics, reports, history, audit.

The six tables that turn findings into a programme somebody can manage
and an auditor can read.
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
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.models.enums import (
    AuditAction,
    JobStatus,
    RemediationKind,
    RemediationStatus,
    ReportFormat,
    ReportKind,
    RiskCategory,
    RiskImpact,
    RiskLikelihood,
    RiskSeverity,
    RiskStatus,
    ScoreGrade,
    ScoreScope,
)


class RiskRegisterEntry(BaseModel):
    """``compliance_risk_register`` -- one tracked risk."""

    __tablename__ = "compliance_risk_register"
    __table_args__ = (
        UniqueConstraint("organization_id", "reference", name="uq_compliance_risk_reference"),
        Index("ix_compliance_risk_org", "organization_id", "status", "severity"),
        Index("ix_compliance_risk_owner", "organization_id", "owner_id"),
        Index("ix_compliance_risk_review", "organization_id", "next_review_at"),
    )

    reference: Mapped[str] = mapped_column(String(64))
    """A human-quotable identifier -- ``RISK-0007``. Assigned by the
    service, unique per organization, and stable for the life of the
    entry, because a risk gets discussed in rooms where nobody is going
    to read out a UUID."""

    title: Mapped[str] = mapped_column(String(512))
    description: Mapped[str | None] = mapped_column(Text, default=None)
    category: Mapped[RiskCategory] = mapped_column(
        String(32), default=RiskCategory.COMPLIANCE, index=True
    )

    likelihood: Mapped[RiskLikelihood] = mapped_column(String(32), default=RiskLikelihood.POSSIBLE)
    impact: Mapped[RiskImpact] = mapped_column(String(32), default=RiskImpact.MODERATE)
    severity: Mapped[RiskSeverity] = mapped_column(
        String(32), default=RiskSeverity.MODERATE, index=True
    )
    """Derived from likelihood and impact by
    :func:`~app.models.enums.severity_for`, never entered. See that
    function for why."""

    inherent_score: Mapped[float] = mapped_column(Float, default=0.0)
    residual_likelihood: Mapped[RiskLikelihood | None] = mapped_column(String(32), default=None)
    residual_impact: Mapped[RiskImpact | None] = mapped_column(String(32), default=None)
    residual_severity: Mapped[RiskSeverity | None] = mapped_column(
        String(32), default=None, index=True
    )
    residual_score: Mapped[float | None] = mapped_column(Float, default=None)
    """What is left after the mitigation actually in place -- not the one
    that is planned. Residual risk recorded against an unimplemented
    mitigation is the most common way a register comes to understate
    exactly what it exists to track."""

    status: Mapped[RiskStatus] = mapped_column(
        String(32), default=RiskStatus.IDENTIFIED, index=True
    )
    owner_id: Mapped[str | None] = mapped_column(String(255), default=None)
    owner_team: Mapped[str | None] = mapped_column(String(255), default=None)

    mitigation_plan: Mapped[str | None] = mapped_column(Text, default=None)
    mitigation_status: Mapped[str | None] = mapped_column(String(255), default=None)
    treatment: Mapped[str | None] = mapped_column(String(64), default=None)

    control_ids: Mapped[list[str]] = mapped_column(JSON, default=list)
    finding_ids: Mapped[list[str]] = mapped_column(JSON, default=list)

    identified_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    next_review_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), default=None, index=True
    )
    last_reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
    review_interval_days: Mapped[int] = mapped_column(Integer, default=90)
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
    closure_reason: Mapped[str | None] = mapped_column(Text, default=None)

    tags: Mapped[list[str]] = mapped_column(JSON, default=list)
    attributes: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)


class RemediationTask(BaseModel):
    """``compliance_remediation`` -- how a finding gets fixed."""

    __tablename__ = "compliance_remediation"
    __table_args__ = (
        Index("ix_compliance_remediation_org", "organization_id", "status"),
        Index("ix_compliance_remediation_finding", "organization_id", "finding_id"),
        Index("ix_compliance_remediation_assignee", "organization_id", "assignee_id"),
    )

    finding_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("compliance_findings.id", ondelete="CASCADE"), default=None, index=True
    )
    control_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("compliance_controls.id", ondelete="SET NULL"), default=None, index=True
    )

    title: Mapped[str] = mapped_column(String(512))
    description: Mapped[str | None] = mapped_column(Text, default=None)
    kind: Mapped[RemediationKind] = mapped_column(String(32), default=RemediationKind.MANUAL)
    status: Mapped[RemediationStatus] = mapped_column(
        String(32), default=RemediationStatus.PROPOSED, index=True
    )

    recommended_action: Mapped[str | None] = mapped_column(Text, default=None)
    playbook_id: Mapped[str | None] = mapped_column(String(255), default=None)
    workflow_id: Mapped[str | None] = mapped_column(String(255), default=None)
    automation_job_id: Mapped[str | None] = mapped_column(String(255), default=None)
    configuration_reference: Mapped[str | None] = mapped_column(String(512), default=None)

    assignee_id: Mapped[str | None] = mapped_column(String(255), default=None)
    due_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)

    verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
    verified_by: Mapped[str | None] = mapped_column(String(255), default=None)
    verification_result_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("compliance_results.id", ondelete="SET NULL"), default=None
    )
    """The re-assessment that proved the fix worked.

    Verification is a *result*, not a checkbox. "We ran the playbook" and
    "the control now passes" are different claims, and only the second
    one may close a finding -- an automated remediation that failed
    silently would otherwise close the finding it did not fix."""

    verification_note: Mapped[str | None] = mapped_column(Text, default=None)
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    error: Mapped[str | None] = mapped_column(Text, default=None)
    attributes: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)


class ComplianceScore(BaseModel):
    """``compliance_scores`` -- a computed score, kept for trending."""

    __tablename__ = "compliance_scores"
    __table_args__ = (
        Index("ix_compliance_score_org", "organization_id", "computed_at"),
        Index("ix_compliance_score_scope", "organization_id", "scope", "scope_id"),
    )

    scope: Mapped[ScoreScope] = mapped_column(String(32), default=ScoreScope.OVERALL, index=True)
    scope_id: Mapped[str | None] = mapped_column(String(255), default=None, index=True)
    scope_name: Mapped[str | None] = mapped_column(String(512), default=None)

    framework_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("compliance_frameworks.id", ondelete="CASCADE"), default=None, index=True
    )
    assessment_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("compliance_assessments.id", ondelete="SET NULL"), default=None
    )

    score: Mapped[float] = mapped_column(Float, default=0.0)
    grade: Mapped[ScoreGrade] = mapped_column(String(32), default=ScoreGrade.CRITICAL)
    weighted_score: Mapped[float] = mapped_column(Float, default=0.0)
    raw_pass_rate: Mapped[float] = mapped_column(Float, default=0.0)
    """The unweighted percentage, kept alongside the weighted one.

    Stored because the *difference* between them is informative: a high
    raw rate next to a low weighted score says the failures are
    concentrated in the controls that matter, which is a different
    problem -- and a more urgent one -- than failing evenly."""

    controls_total: Mapped[int] = mapped_column(Integer, default=0)
    controls_passed: Mapped[int] = mapped_column(Integer, default=0)
    controls_failed: Mapped[int] = mapped_column(Integer, default=0)
    controls_excepted: Mapped[int] = mapped_column(Integer, default=0)
    controls_not_applicable: Mapped[int] = mapped_column(Integer, default=0)

    previous_score: Mapped[float | None] = mapped_column(Float, default=None)
    delta: Mapped[float | None] = mapped_column(Float, default=None)
    computed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    breakdown: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)


class ComplianceStatistic(BaseModel):
    """``compliance_statistics`` -- one rolled-up window."""

    __tablename__ = "compliance_statistics"
    __table_args__ = (Index("ix_compliance_statistic_org", "organization_id", "window_start"),)

    window_start: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    window_end: Mapped[datetime] = mapped_column(DateTime(timezone=True))

    assessments_run: Mapped[int] = mapped_column(Integer, default=0)
    assessments_failed: Mapped[int] = mapped_column(Integer, default=0)
    scans_run: Mapped[int] = mapped_column(Integer, default=0)
    controls_evaluated: Mapped[int] = mapped_column(Integer, default=0)
    evidence_collected: Mapped[int] = mapped_column(Integer, default=0)

    findings_opened: Mapped[int] = mapped_column(Integer, default=0)
    findings_resolved: Mapped[int] = mapped_column(Integer, default=0)
    findings_open_total: Mapped[int] = mapped_column(Integer, default=0)
    findings_critical: Mapped[int] = mapped_column(Integer, default=0)

    risks_registered: Mapped[int] = mapped_column(Integer, default=0)
    risks_open_total: Mapped[int] = mapped_column(Integer, default=0)
    exceptions_active: Mapped[int] = mapped_column(Integer, default=0)
    exceptions_expiring: Mapped[int] = mapped_column(Integer, default=0)

    remediations_completed: Mapped[int] = mapped_column(Integer, default=0)
    remediations_verified: Mapped[int] = mapped_column(Integer, default=0)
    remediation_success_rate: Mapped[float] = mapped_column(Float, default=0.0)

    average_score: Mapped[float] = mapped_column(Float, default=0.0)
    framework_coverage: Mapped[float] = mapped_column(Float, default=0.0)
    control_coverage: Mapped[float] = mapped_column(Float, default=0.0)
    breakdown: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)


class ComplianceReport(BaseModel):
    """``compliance_reports`` -- a generated document."""

    __tablename__ = "compliance_reports"
    __table_args__ = (Index("ix_compliance_report_org", "organization_id", "generated_at"),)

    kind: Mapped[ReportKind] = mapped_column(String(32), index=True)
    report_format: Mapped[ReportFormat] = mapped_column(String(16), default=ReportFormat.JSON)
    title: Mapped[str] = mapped_column(String(512))
    status: Mapped[JobStatus] = mapped_column(String(32), default=JobStatus.PENDING, index=True)

    framework_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("compliance_frameworks.id", ondelete="SET NULL"), default=None
    )
    assessment_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("compliance_assessments.id", ondelete="SET NULL"), default=None
    )

    period_start: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
    period_end: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)

    generated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), default=None, index=True
    )
    generated_by: Mapped[str | None] = mapped_column(String(255), default=None)
    duration_ms: Mapped[float | None] = mapped_column(Float, default=None)

    content: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    row_count: Mapped[int] = mapped_column(Integer, default=0)
    error: Mapped[str | None] = mapped_column(Text, default=None)
    parameters: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)


class ComplianceHistory(BaseModel):
    """``compliance_history`` -- what changed, for trend and for proof.

    Separate from :class:`ComplianceAudit`. History records *state over
    time* -- this control was implemented on the 4th, this score moved
    from 82 to 87 -- and is what trend reporting reads. Audit records
    *who did what*. Merging them produces a table that is too noisy to
    trend and too lossy to audit.
    """

    __tablename__ = "compliance_history"
    __table_args__ = (
        Index("ix_compliance_history_org", "organization_id", "recorded_at"),
        Index("ix_compliance_history_entity", "organization_id", "entity_type", "entity_id"),
    )

    entity_type: Mapped[str] = mapped_column(String(64), index=True)
    entity_id: Mapped[uuid.UUID | None] = mapped_column(default=None, index=True)
    entity_reference: Mapped[str | None] = mapped_column(String(255), default=None)

    field: Mapped[str | None] = mapped_column(String(128), default=None)
    previous_value: Mapped[str | None] = mapped_column(Text, default=None)
    new_value: Mapped[str | None] = mapped_column(Text, default=None)
    numeric_value: Mapped[float | None] = mapped_column(Float, default=None)

    recorded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    note: Mapped[str | None] = mapped_column(Text, default=None)
    snapshot: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)


class ComplianceAudit(BaseModel):
    """``compliance_audit`` -- append-only record of who did what.

    Never updated and never deleted, which is why it carries its own
    ``occurred_at`` rather than relying on ``created_at``: the base
    entity's timestamps describe the row, and an audit trail has to
    describe the event even if the two ever diverge.
    """

    __tablename__ = "compliance_audit"
    __table_args__ = (
        Index("ix_compliance_audit_org", "organization_id", "occurred_at"),
        Index("ix_compliance_audit_action", "organization_id", "action"),
        Index("ix_compliance_audit_actor", "organization_id", "actor_id"),
    )

    action: Mapped[AuditAction] = mapped_column(String(64), index=True)
    entity_type: Mapped[str] = mapped_column(String(64), index=True)
    entity_id: Mapped[uuid.UUID | None] = mapped_column(default=None, index=True)
    entity_reference: Mapped[str | None] = mapped_column(String(255), default=None)

    actor_id: Mapped[str | None] = mapped_column(String(255), default=None, index=True)
    actor_type: Mapped[str] = mapped_column(String(32), default="user")
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)

    summary: Mapped[str] = mapped_column(Text)
    succeeded: Mapped[bool] = mapped_column(Boolean, default=True)
    ip_address: Mapped[str | None] = mapped_column(String(64), default=None)
    request_id: Mapped[str | None] = mapped_column(String(64), default=None)
    changes: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    context: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)


__all__ = [
    "ComplianceAudit",
    "ComplianceHistory",
    "ComplianceReport",
    "ComplianceScore",
    "ComplianceStatistic",
    "RemediationTask",
    "RiskRegisterEntry",
]
