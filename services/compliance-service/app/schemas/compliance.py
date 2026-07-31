"""Request and response shapes for the compliance API.

Bounded everywhere: every string has a max length and every list a max
size. This service accepts evidence payloads and rule trees from
collectors, which means it accepts arbitrary documents from automated
callers -- and the ceiling that is not stated is the one somebody
eventually exceeds.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.models.enums import (
    AssessmentKind,
    AssessmentScope,
    AssessmentStatus,
    ControlCategory,
    ControlRelationKind,
    ControlSeverity,
    ControlStatus,
    EvidenceKind,
    EvidenceSource,
    ExceptionKind,
    ExceptionStatus,
    FindingSeverity,
    FindingStatus,
    FrameworkCode,
    FrameworkKind,
    FrameworkStatus,
    RemediationKind,
    RemediationStatus,
    ReportFormat,
    ReportKind,
    ResultStatus,
    RiskCategory,
    RiskImpact,
    RiskLikelihood,
    RiskStatus,
    ScoreScope,
)
from app.rules.engine import CheckOperator, LogicalOperator

MAX_RULE_CHECKS = 100
MAX_TARGETS = 500
MAX_TAGS = 50


# ---- rules ------------------------------------------------------------


class CheckPayload(BaseModel):
    """One comparison inside a control's rule."""

    path: str = Field(min_length=1, max_length=512)
    operator: CheckOperator
    value: Any = None
    negate: bool = False
    description: str | None = Field(default=None, max_length=1_000)


class RulePayload(BaseModel):
    """A logical combination of checks and nested rules."""

    name: str = Field(default="rule", max_length=255)
    logical_operator: LogicalOperator = LogicalOperator.ALL
    checks: list[CheckPayload] = Field(default_factory=list, max_length=MAX_RULE_CHECKS)
    children: list[RulePayload] = Field(default_factory=list, max_length=32)
    negate: bool = False
    description: str | None = Field(default=None, max_length=1_000)


RulePayload.model_rebuild()


# ---- frameworks and controls -------------------------------------------


class FrameworkCreateRequest(BaseModel):
    """Register a framework."""

    slug: str = Field(min_length=1, max_length=255, pattern=r"^[a-z0-9][a-z0-9\-]*$")
    name: str = Field(min_length=1, max_length=255)
    code: FrameworkCode = FrameworkCode.CUSTOM
    kind: FrameworkKind = FrameworkKind.CUSTOM
    description: str | None = Field(default=None, max_length=4_000)
    publisher: str | None = Field(default=None, max_length=255)
    framework_version: str = Field(default="1.0.0", max_length=64)
    reference_url: str | None = Field(default=None, max_length=1_024)
    weight: float = Field(default=1.0, ge=0.0, le=100.0)
    tags: list[str] = Field(default_factory=list, max_length=MAX_TAGS)


class FrameworkUpdateRequest(BaseModel):
    """Change a framework's metadata."""

    name: str | None = Field(default=None, max_length=255)
    description: str | None = Field(default=None, max_length=4_000)
    status: FrameworkStatus | None = None
    weight: float | None = Field(default=None, ge=0.0, le=100.0)
    tags: list[str] | None = Field(default=None, max_length=MAX_TAGS)


class FrameworkResponse(BaseModel):
    """One framework."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    slug: str
    name: str
    description: str | None
    code: str
    kind: str
    status: str
    publisher: str | None
    framework_version: str
    reference_url: str | None
    weight: float
    control_count: int
    is_builtin: bool
    tags: list[str]
    created_at: datetime
    updated_at: datetime | None


class ControlCreateRequest(BaseModel):
    """Add a control to a framework."""

    code: str = Field(min_length=1, max_length=128)
    title: str = Field(min_length=1, max_length=512)
    description: str | None = Field(default=None, max_length=8_000)
    guidance: str | None = Field(default=None, max_length=8_000)
    category: ControlCategory = ControlCategory.OTHER
    severity: ControlSeverity = ControlSeverity.MEDIUM
    status: ControlStatus = ControlStatus.NOT_IMPLEMENTED
    owner_id: str | None = Field(default=None, max_length=255)
    owner_team: str | None = Field(default=None, max_length=255)
    rule: RulePayload | None = None
    remediation_guidance: str | None = Field(default=None, max_length=8_000)
    references: list[str] = Field(default_factory=list, max_length=MAX_TAGS)
    tags: list[str] = Field(default_factory=list, max_length=MAX_TAGS)


class ControlUpdateRequest(BaseModel):
    """Change a control's metadata or ownership."""

    title: str | None = Field(default=None, max_length=512)
    description: str | None = Field(default=None, max_length=8_000)
    severity: ControlSeverity | None = None
    status: ControlStatus | None = None
    owner_id: str | None = Field(default=None, max_length=255)
    owner_team: str | None = Field(default=None, max_length=255)
    remediation_guidance: str | None = Field(default=None, max_length=8_000)
    tags: list[str] | None = Field(default=None, max_length=MAX_TAGS)


class ControlRuleRequest(BaseModel):
    """Give a control a machine-checkable rule."""

    rule: RulePayload


class ControlResponse(BaseModel):
    """One control."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    framework_id: UUID
    code: str
    title: str
    description: str | None
    guidance: str | None
    category: str
    severity: str
    status: str
    owner_id: str | None
    owner_team: str | None
    control_version: int
    is_builtin: bool
    is_automatable: bool
    rule: dict[str, Any]
    remediation_guidance: str | None
    references: list[str]
    tags: list[str]
    created_at: datetime
    updated_at: datetime | None


class ControlMappingRequest(BaseModel):
    """Record that two controls ask related questions."""

    source_control_id: UUID
    target_control_id: UUID
    relation: ControlRelationKind = ControlRelationKind.EQUIVALENT_TO
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)
    note: str | None = Field(default=None, max_length=2_000)


class ControlMappingResponse(BaseModel):
    """One mapping."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    source_control_id: UUID
    target_control_id: UUID
    relation: str
    confidence: float
    note: str | None


# ---- assessments --------------------------------------------------------


class TargetPayload(BaseModel):
    """One thing to assess, and what is known about it."""

    target_id: str = Field(min_length=1, max_length=255)
    target_type: str = Field(default="asset", max_length=64)
    name: str | None = Field(default=None, max_length=512)
    payload: dict[str, Any] = Field(default_factory=dict)
    """Collected evidence for this target.

    Optional: a target named without one is filled from stored evidence,
    which is what makes a historical assessment reproducible.
    """

    evidence_id: str | None = Field(default=None, max_length=64)


class AssessmentCreateRequest(BaseModel):
    """Plan an assessment."""

    name: str = Field(min_length=1, max_length=255)
    description: str | None = Field(default=None, max_length=4_000)
    kind: AssessmentKind = AssessmentKind.ON_DEMAND
    scope: AssessmentScope = AssessmentScope.ORGANIZATION
    scope_id: str | None = Field(default=None, max_length=255)
    framework_id: UUID | None = None
    parameters: dict[str, Any] = Field(default_factory=dict)


class AssessmentRunRequest(BaseModel):
    """Execute a planned assessment."""

    targets: list[TargetPayload] = Field(default_factory=list, max_length=MAX_TARGETS)
    notify_user_id: str | None = Field(default=None, max_length=255)
    raise_findings: bool = True
    """Whether failures become findings.

    On by default. Off is for a rehearsal -- somebody checking what a new
    control would flag before committing to owning the queue it creates.
    """


class AssessmentResponse(BaseModel):
    """One assessment."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    description: str | None
    kind: str
    scope: str
    scope_id: str | None
    status: str
    framework_id: UUID | None
    started_at: datetime | None
    completed_at: datetime | None
    duration_ms: float | None
    controls_total: int
    controls_passed: int
    controls_failed: int
    controls_warning: int
    controls_not_applicable: int
    controls_not_assessed: int
    controls_errored: int
    controls_excepted: int
    score: float | None
    findings_raised: int
    error: str | None
    summary: dict[str, Any]
    created_at: datetime


class ResultResponse(BaseModel):
    """One control's verdict on one target."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    assessment_id: UUID | None
    control_id: UUID
    framework_id: UUID | None
    target_type: str | None
    target_id: str | None
    target_name: str | None
    status: str
    reason: str | None
    evaluated_at: datetime | None
    evidence_id: UUID | None
    exception_id: UUID | None
    error: str | None


class ScanRequest(BaseModel):
    """Record a collector pass and the evidence it gathered."""

    name: str = Field(min_length=1, max_length=255)
    kind: str = Field(default="compliance", max_length=32)
    assessment_id: UUID | None = None
    target_type: str | None = Field(default=None, max_length=64)
    target_id: str | None = Field(default=None, max_length=255)
    scanner: str = Field(default="builtin", max_length=128)
    is_incremental: bool = False
    targets: list[TargetPayload] = Field(default_factory=list, max_length=MAX_TARGETS)
    parameters: dict[str, Any] = Field(default_factory=dict)


class ScanResponse(BaseModel):
    """One scan."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    assessment_id: UUID | None
    name: str
    kind: str
    status: str
    target_type: str | None
    target_id: str | None
    scanner: str
    started_at: datetime | None
    completed_at: datetime | None
    duration_ms: float | None
    targets_scanned: int
    checks_run: int
    checks_failed: int
    is_incremental: bool
    error: str | None


# ---- evidence -----------------------------------------------------------


class EvidenceCreateRequest(BaseModel):
    """Record one piece of proof."""

    kind: EvidenceKind
    source: EvidenceSource
    title: str = Field(min_length=1, max_length=512)
    payload: dict[str, Any]
    control_id: UUID | None = None
    assessment_id: UUID | None = None
    target_type: str | None = Field(default=None, max_length=64)
    target_id: str | None = Field(default=None, max_length=255)
    source_reference: str | None = Field(default=None, max_length=512)
    description: str | None = Field(default=None, max_length=4_000)
    collected_by: str | None = Field(default=None, max_length=255)
    validity_days: int | None = Field(default=None, ge=1, le=3_650)
    content_type: str | None = Field(default=None, max_length=128)
    storage_key: str | None = Field(default=None, max_length=1_024)
    tags: list[str] = Field(default_factory=list, max_length=MAX_TAGS)


class EvidenceSupersedeRequest(BaseModel):
    """Correct evidence by replacing it."""

    payload: dict[str, Any]
    title: str | None = Field(default=None, max_length=512)
    reason: str | None = Field(default=None, max_length=4_000)
    collected_by: str | None = Field(default=None, max_length=255)


class EvidenceResponse(BaseModel):
    """One piece of evidence.

    Carries ``intact``, which is recomputed on read rather than stored.
    A stored "verified" flag would be as forgeable as the row it
    describes, which defeats the point of having a digest at all.
    """

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    assessment_id: UUID | None
    control_id: UUID | None
    kind: str
    source: str
    source_reference: str | None
    title: str
    description: str | None
    target_type: str | None
    target_id: str | None
    payload: dict[str, Any]
    digest: str
    collected_at: datetime
    collected_by: str | None
    expires_at: datetime | None
    supersedes_id: UUID | None
    is_superseded: bool
    size_bytes: int
    tags: list[str]


# ---- findings ------------------------------------------------------------


class FindingUpdateRequest(BaseModel):
    """Move a finding through its lifecycle."""

    status: FindingStatus
    note: str | None = Field(default=None, max_length=4_000)


class FindingAssignRequest(BaseModel):
    """Give a finding an owner."""

    assignee_id: str = Field(min_length=1, max_length=255)


class FindingResponse(BaseModel):
    """One finding."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    assessment_id: UUID | None
    control_id: UUID
    framework_id: UUID | None
    title: str
    description: str | None
    severity: str
    status: str
    fingerprint: str
    target_type: str | None
    target_id: str | None
    target_name: str | None
    risk_score: float
    assignee_id: str | None
    due_at: datetime | None
    first_detected_at: datetime
    last_detected_at: datetime
    detection_count: int
    resolved_at: datetime | None
    resolution_note: str | None
    exception_id: UUID | None


# ---- exceptions -----------------------------------------------------------


class ExceptionCreateRequest(BaseModel):
    """Ask for a control to be waived."""

    control_id: UUID
    title: str = Field(min_length=1, max_length=512)
    business_justification: str = Field(min_length=1, max_length=8_000)
    kind: ExceptionKind = ExceptionKind.TEMPORARY
    expires_at: datetime | None = None
    risk_acceptance: str | None = Field(default=None, max_length=4_000)
    compensating_control: str | None = Field(default=None, max_length=4_000)
    target_type: str | None = Field(default=None, max_length=64)
    target_id: str | None = Field(default=None, max_length=255)
    review_interval_days: int | None = Field(default=None, ge=1, le=730)
    requested_by: str | None = Field(default=None, max_length=255)


class ExceptionDecisionRequest(BaseModel):
    """Approve or refuse a requested waiver."""

    approve: bool
    decided_by: str = Field(min_length=1, max_length=255)
    reason: str | None = Field(default=None, max_length=4_000)


class ExceptionReviewRequest(BaseModel):
    """Record a periodic review."""

    reviewed_by: str = Field(min_length=1, max_length=255)
    still_needed: bool
    note: str | None = Field(default=None, max_length=4_000)


class ExceptionRevokeRequest(BaseModel):
    """End a live waiver early."""

    reason: str = Field(min_length=1, max_length=4_000)


class ExceptionResponse(BaseModel):
    """One exception."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    control_id: UUID
    title: str
    kind: str
    status: str
    business_justification: str
    risk_acceptance: str | None
    compensating_control: str | None
    target_type: str | None
    target_id: str | None
    requested_by: str | None
    approved_by: str | None
    approved_at: datetime | None
    effective_from: datetime | None
    expires_at: datetime | None
    next_review_at: datetime | None
    last_reviewed_at: datetime | None
    revoked_at: datetime | None
    revocation_reason: str | None
    use_count: int
    created_at: datetime


# ---- risk ----------------------------------------------------------------


class RiskCreateRequest(BaseModel):
    """Add a risk to the register.

    There is deliberately no ``severity`` field. It is derived from
    likelihood and impact, because a register that accepts a severity
    lets the person who owns a risk grade their own risk.
    """

    title: str = Field(min_length=1, max_length=512)
    likelihood: RiskLikelihood
    impact: RiskImpact
    category: RiskCategory = RiskCategory.COMPLIANCE
    description: str | None = Field(default=None, max_length=8_000)
    owner_id: str | None = Field(default=None, max_length=255)
    owner_team: str | None = Field(default=None, max_length=255)
    mitigation_plan: str | None = Field(default=None, max_length=8_000)
    control_ids: list[str] = Field(default_factory=list, max_length=200)
    finding_ids: list[str] = Field(default_factory=list, max_length=200)
    review_interval_days: int | None = Field(default=None, ge=1, le=730)
    notify_user_id: str | None = Field(default=None, max_length=255)


class RiskAssessRequest(BaseModel):
    """Re-score a risk, inherent or residual."""

    likelihood: RiskLikelihood | None = None
    impact: RiskImpact | None = None
    residual_likelihood: RiskLikelihood | None = None
    residual_impact: RiskImpact | None = None


class RiskTransitionRequest(BaseModel):
    """Move a risk through its lifecycle."""

    status: RiskStatus
    reason: str | None = Field(default=None, max_length=4_000)


class RiskResponse(BaseModel):
    """One risk."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    reference: str
    title: str
    description: str | None
    category: str
    likelihood: str
    impact: str
    severity: str
    inherent_score: float
    residual_likelihood: str | None
    residual_impact: str | None
    residual_severity: str | None
    residual_score: float | None
    status: str
    owner_id: str | None
    owner_team: str | None
    mitigation_plan: str | None
    control_ids: list[str]
    finding_ids: list[str]
    identified_at: datetime
    next_review_at: datetime | None
    last_reviewed_at: datetime | None
    closed_at: datetime | None
    closure_reason: str | None


# ---- remediation ----------------------------------------------------------


class RemediationCreateRequest(BaseModel):
    """Propose a fix for a finding."""

    finding_id: UUID
    title: str = Field(min_length=1, max_length=512)
    kind: RemediationKind = RemediationKind.MANUAL
    description: str | None = Field(default=None, max_length=8_000)
    recommended_action: str | None = Field(default=None, max_length=8_000)
    playbook_id: str | None = Field(default=None, max_length=255)
    workflow_id: str | None = Field(default=None, max_length=255)
    automation_job_id: str | None = Field(default=None, max_length=255)
    assignee_id: str | None = Field(default=None, max_length=255)
    due_at: datetime | None = None


class RemediationTransitionRequest(BaseModel):
    """Move a remediation through its lifecycle."""

    status: RemediationStatus
    note: str | None = Field(default=None, max_length=4_000)


class RemediationVerifyRequest(BaseModel):
    """Check whether the control actually passes now."""

    verified_by: str = Field(min_length=1, max_length=255)
    notify_user_id: str | None = Field(default=None, max_length=255)


class RemediationResponse(BaseModel):
    """One remediation task."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    finding_id: UUID | None
    control_id: UUID | None
    title: str
    description: str | None
    kind: str
    status: str
    recommended_action: str | None
    playbook_id: str | None
    workflow_id: str | None
    automation_job_id: str | None
    assignee_id: str | None
    due_at: datetime | None
    started_at: datetime | None
    completed_at: datetime | None
    verified_at: datetime | None
    verified_by: str | None
    verification_result_id: UUID | None
    verification_note: str | None
    attempts: int
    error: str | None


# ---- scores and reports ---------------------------------------------------


class ScoreResponse(BaseModel):
    """One stored score."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    scope: str
    scope_id: str | None
    scope_name: str | None
    framework_id: UUID | None
    assessment_id: UUID | None
    score: float
    grade: str
    weighted_score: float
    raw_pass_rate: float
    controls_total: int
    controls_passed: int
    controls_failed: int
    controls_excepted: int
    controls_not_applicable: int
    previous_score: float | None
    delta: float | None
    computed_at: datetime
    breakdown: dict[str, Any]


class ReportRequest(BaseModel):
    """Ask for a report."""

    kind: ReportKind
    report_format: ReportFormat = ReportFormat.JSON
    title: str | None = Field(default=None, max_length=512)
    framework_id: UUID | None = None
    assessment_id: UUID | None = None
    period_days: int = Field(default=90, ge=1, le=3_650)


class ReportResponse(BaseModel):
    """One generated report."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    kind: str
    report_format: str
    title: str
    status: str
    framework_id: UUID | None
    assessment_id: UUID | None
    period_start: datetime | None
    period_end: datetime | None
    generated_at: datetime | None
    duration_ms: float | None
    row_count: int
    error: str | None
    content: dict[str, Any]


class AuditResponse(BaseModel):
    """One audit entry."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    action: str
    entity_type: str
    entity_id: UUID | None
    entity_reference: str | None
    actor_id: str | None
    actor_type: str
    occurred_at: datetime
    summary: str
    succeeded: bool
    changes: dict[str, Any]


class StatisticResponse(BaseModel):
    """One rolled-up window."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    window_start: datetime
    window_end: datetime
    assessments_run: int
    assessments_failed: int
    scans_run: int
    controls_evaluated: int
    evidence_collected: int
    findings_opened: int
    findings_resolved: int
    findings_open_total: int
    findings_critical: int
    risks_registered: int
    risks_open_total: int
    exceptions_active: int
    exceptions_expiring: int
    remediations_completed: int
    remediations_verified: int
    remediation_success_rate: float
    average_score: float
    framework_coverage: float
    control_coverage: float
    breakdown: dict[str, Any]


# ---- filters ---------------------------------------------------------------


class FindingFilters(BaseModel):
    """Query parameters for listing findings."""

    status: FindingStatus | None = None
    severity: FindingSeverity | None = None
    control_id: UUID | None = None
    framework_id: UUID | None = None
    assignee_id: str | None = None
    target_id: str | None = None
    open_only: bool = False


class ScoreQuery(BaseModel):
    """Query parameters for reading a score."""

    scope: ScoreScope = ScoreScope.OVERALL
    scope_id: str | None = None


class ResultFilters(BaseModel):
    """Query parameters for listing results."""

    status: ResultStatus | None = None


class AssessmentFilters(BaseModel):
    """Query parameters for listing assessments."""

    status: AssessmentStatus | None = None
    framework_id: UUID | None = None


class ExceptionFilters(BaseModel):
    """Query parameters for listing exceptions."""

    status: ExceptionStatus | None = None
    control_id: UUID | None = None


__all__ = [
    "MAX_RULE_CHECKS",
    "MAX_TAGS",
    "MAX_TARGETS",
    "AssessmentCreateRequest",
    "AssessmentFilters",
    "AssessmentResponse",
    "AssessmentRunRequest",
    "AuditResponse",
    "CheckPayload",
    "ControlCreateRequest",
    "ControlMappingRequest",
    "ControlMappingResponse",
    "ControlResponse",
    "ControlRuleRequest",
    "ControlUpdateRequest",
    "EvidenceCreateRequest",
    "EvidenceResponse",
    "EvidenceSupersedeRequest",
    "ExceptionCreateRequest",
    "ExceptionDecisionRequest",
    "ExceptionFilters",
    "ExceptionResponse",
    "ExceptionReviewRequest",
    "ExceptionRevokeRequest",
    "FindingAssignRequest",
    "FindingFilters",
    "FindingResponse",
    "FindingUpdateRequest",
    "FrameworkCreateRequest",
    "FrameworkResponse",
    "FrameworkUpdateRequest",
    "RemediationCreateRequest",
    "RemediationResponse",
    "RemediationTransitionRequest",
    "RemediationVerifyRequest",
    "ReportRequest",
    "ReportResponse",
    "ResultFilters",
    "ResultResponse",
    "RiskAssessRequest",
    "RiskCreateRequest",
    "RiskResponse",
    "RiskTransitionRequest",
    "RulePayload",
    "ScanRequest",
    "ScanResponse",
    "ScoreQuery",
    "ScoreResponse",
    "StatisticResponse",
    "TargetPayload",
]
