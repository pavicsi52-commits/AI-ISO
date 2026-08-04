"""Request and response shapes for the change management API.

Bounded everywhere: every string has a max length and every list a max
size, the same discipline Prompt 052 applies -- this service accepts
input from requesters, CAB members, and automated implementation
tooling, none of which this service controls the shape of.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.models.enums import (
    ApprovalPolicy,
    ApprovalStatus,
    CabVote,
    CalendarEntryKind,
    ChangeCategory,
    ChangePriority,
    ChangeTaskStatus,
    ChangeType,
    ConflictStatus,
    PirStatus,
    RecurrenceKind,
    RelationshipKind,
    ReportFormat,
    ReportKind,
    RiskImpact,
    RiskLevel,
    RiskLikelihood,
    RollbackStatus,
    ValidationKind,
    ValidationStatus,
)

MAX_TAGS = 50
MAX_APPROVERS = 20
MAX_INVITED = 100
MAX_ASSETS_PER_CHANGE = 500

# ---- changes --------------------------------------------------------------


class ChangeCreateRequest(BaseModel):
    """Open a new change request."""

    title: str = Field(min_length=1, max_length=512)
    description: str | None = Field(default=None, max_length=8_000)
    business_justification: str | None = Field(default=None, max_length=4_000)
    requester_id: str = Field(min_length=1, max_length=255)
    business_owner_id: str | None = Field(default=None, max_length=255)
    technical_owner_id: str | None = Field(default=None, max_length=255)
    category: ChangeCategory = ChangeCategory.CUSTOM
    change_type: ChangeType = ChangeType.NORMAL
    priority: ChangePriority = ChangePriority.MEDIUM
    affected_assets: list[str] = Field(default_factory=list, max_length=MAX_ASSETS_PER_CHANGE)
    affected_services: list[str] = Field(default_factory=list, max_length=MAX_ASSETS_PER_CHANGE)
    affected_applications: list[str] = Field(default_factory=list, max_length=MAX_ASSETS_PER_CHANGE)
    implementation_plan: str | None = Field(default=None, max_length=16_000)
    validation_plan: str | None = Field(default=None, max_length=16_000)
    rollback_plan: str | None = Field(default=None, max_length=16_000)
    incident_id: str | None = Field(default=None, max_length=64)
    problem_id: str | None = Field(default=None, max_length=64)
    known_error_id: str | None = Field(default=None, max_length=64)
    tags: list[str] = Field(default_factory=list, max_length=MAX_TAGS)


class ChangeUpdateRequest(BaseModel):
    """Edit a draft change's own content fields. Every field is optional."""

    title: str | None = Field(default=None, min_length=1, max_length=512)
    description: str | None = Field(default=None, max_length=8_000)
    business_justification: str | None = Field(default=None, max_length=4_000)
    business_owner_id: str | None = Field(default=None, max_length=255)
    technical_owner_id: str | None = Field(default=None, max_length=255)
    category: ChangeCategory | None = None
    change_type: ChangeType | None = None
    priority: ChangePriority | None = None
    affected_assets: list[str] | None = Field(default=None, max_length=MAX_ASSETS_PER_CHANGE)
    affected_services: list[str] | None = Field(default=None, max_length=MAX_ASSETS_PER_CHANGE)
    affected_applications: list[str] | None = Field(default=None, max_length=MAX_ASSETS_PER_CHANGE)
    implementation_plan: str | None = Field(default=None, max_length=16_000)
    validation_plan: str | None = Field(default=None, max_length=16_000)
    rollback_plan: str | None = Field(default=None, max_length=16_000)
    tags: list[str] | None = Field(default=None, max_length=MAX_TAGS)


class ChangeScheduleRequest(BaseModel):
    """Book a change into a maintenance window."""

    calendar_entry_id: UUID
    scheduled_start_at: datetime
    scheduled_end_at: datetime


class ChangeRelationshipRequest(BaseModel):
    """Relate one change to another."""

    related_change_id: UUID
    kind: RelationshipKind
    note: str | None = Field(default=None, max_length=2_000)


class ChangeRelationshipResponse(BaseModel):
    """One change-to-change relationship."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    change_id: UUID
    related_change_id: UUID
    kind: RelationshipKind
    note: str | None


class ChangeResponse(BaseModel):
    """One change request."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    reference: str
    title: str
    description: str | None
    business_justification: str | None
    requester_id: str
    business_owner_id: str | None
    technical_owner_id: str | None
    category: str
    change_type: str
    priority: str
    status: str
    risk_level: str | None
    affected_assets: list[str]
    affected_services: list[str]
    affected_applications: list[str]
    implementation_plan: str | None
    validation_plan: str | None
    rollback_plan: str | None
    cab_required: bool
    calendar_entry_id: UUID | None
    incident_id: str | None
    problem_id: str | None
    known_error_id: str | None
    submitted_at: datetime | None
    approved_at: datetime | None
    scheduled_start_at: datetime | None
    scheduled_end_at: datetime | None
    actual_start_at: datetime | None
    actual_end_at: datetime | None
    completed_at: datetime | None
    closed_at: datetime | None
    approval_duration_seconds: float | None
    implementation_duration_seconds: float | None
    tags: list[str]
    created_at: datetime
    updated_at: datetime


# ---- risk -------------------------------------------------------------------


class RiskDimensionsPayload(BaseModel):
    """The six independent risk readings a caller records."""

    technical: RiskImpact
    business: RiskImpact
    operational: RiskImpact
    security: RiskImpact
    compliance: RiskImpact
    dependency: RiskImpact


class RiskAssessRequest(BaseModel):
    """Score and record a risk assessment."""

    likelihood: RiskLikelihood
    dimensions: RiskDimensionsPayload
    assessed_by: str | None = Field(default=None, max_length=255)
    manual_override: RiskLevel | None = None
    override_reason: str | None = Field(default=None, max_length=2_000)
    override_by: str | None = Field(default=None, max_length=255)


class RiskOverrideRequest(BaseModel):
    """Override a recorded assessment's banding."""

    override: RiskLevel
    reason: str = Field(min_length=1, max_length=2_000)
    by: str = Field(min_length=1, max_length=255)


class RiskAssessmentResponse(BaseModel):
    """One risk assessment."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    change_id: UUID
    likelihood: RiskLikelihood
    impact: RiskImpact
    technical_risk: RiskImpact
    business_risk: RiskImpact
    operational_risk: RiskImpact
    security_risk: RiskImpact
    compliance_risk: RiskImpact
    dependency_risk: RiskImpact
    automated_score: float
    risk_level: RiskLevel
    manual_override: RiskLevel | None
    override_reason: str | None
    override_by: str | None
    approval_recommendation: str
    assessed_by: str | None
    assessed_at: datetime


# ---- approvals --------------------------------------------------------------


class ApproverPayload(BaseModel):
    """One approver in a requested chain."""

    approver_id: str = Field(min_length=1, max_length=255)
    approver_role: str | None = Field(default=None, max_length=128)


class ApprovalRequestPayload(BaseModel):
    """Open a change's approval chain."""

    policy: ApprovalPolicy
    approvers: list[ApproverPayload] = Field(min_length=1, max_length=MAX_APPROVERS)


class ApprovalDecideRequest(BaseModel):
    """Record one approver's decision."""

    decision: ApprovalStatus
    comment: str | None = Field(default=None, max_length=2_000)


class ApprovalDelegateRequest(BaseModel):
    """Delegate a pending approval step."""

    delegated_to: str = Field(min_length=1, max_length=255)


class ApprovalResponse(BaseModel):
    """One approval step."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    change_id: UUID
    policy: ApprovalPolicy
    level: int
    approver_id: str
    approver_role: str | None
    status: ApprovalStatus
    comment: str | None
    decided_at: datetime | None
    delegated_to: str | None
    delegated_from: str | None
    expires_at: datetime | None


# ---- CAB ----------------------------------------------------------------------


class CabScheduleRequest(BaseModel):
    """Schedule a CAB review for a change."""

    scheduled_at: datetime
    chair_id: str | None = Field(default=None, max_length=255)
    invited: list[str] = Field(min_length=1, max_length=MAX_INVITED)
    agenda: str | None = Field(default=None, max_length=8_000)
    is_emergency_cab: bool = False
    is_virtual: bool = False


class CabVoteRequest(BaseModel):
    """Cast one vote at a CAB review."""

    voter_id: str = Field(min_length=1, max_length=255)
    vote: CabVote
    comment: str | None = Field(default=None, max_length=2_000)


class CabResponse(BaseModel):
    """One CAB review."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    change_id: UUID
    status: str
    scheduled_at: datetime | None
    held_at: datetime | None
    chair_id: str | None
    is_emergency_cab: bool
    is_virtual: bool
    agenda: str | None
    notes: str | None
    quorum_fraction_required: float
    invited_count: int
    quorum_met: bool | None
    outcome: str | None


class CabVoteResponse(BaseModel):
    """One vote cast at a CAB review."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    cab_id: UUID
    voter_id: str
    vote: CabVote
    comment: str | None
    voted_at: datetime


# ---- calendar -----------------------------------------------------------------


class CalendarEntryCreateRequest(BaseModel):
    """Create a maintenance window or blackout period."""

    kind: CalendarEntryKind
    title: str = Field(min_length=1, max_length=255)
    description: str | None = Field(default=None, max_length=4_000)
    starts_at: datetime
    ends_at: datetime
    timezone: str = Field(default="UTC", max_length=64)
    recurrence: RecurrenceKind = RecurrenceKind.NONE
    recurrence_until: datetime | None = None
    is_org_wide: bool = True
    capacity_limit: int | None = Field(default=None, ge=1)


class CalendarEntryResponse(BaseModel):
    """One calendar entry."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    kind: CalendarEntryKind
    title: str
    description: str | None
    starts_at: datetime
    ends_at: datetime
    timezone: str
    recurrence: RecurrenceKind
    recurrence_until: datetime | None
    is_org_wide: bool
    capacity_limit: int | None


class AvailabilityResponse(BaseModel):
    """Whether a maintenance window still has room."""

    is_available: bool
    reason: str | None


# ---- conflicts ------------------------------------------------------------------


class ConflictResolveRequest(BaseModel):
    """Resolve a detected conflict."""

    resolved_by: str = Field(min_length=1, max_length=255)
    note: str | None = Field(default=None, max_length=2_000)


class ConflictResponse(BaseModel):
    """One detected conflict."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    change_id: UUID
    conflicting_change_id: UUID
    kind: str
    status: ConflictStatus
    detail: str
    detected_at: datetime
    resolved_by: str | None
    resolved_at: datetime | None
    resolution_note: str | None


# ---- implementation -------------------------------------------------------------


class TaskCreateRequest(BaseModel):
    """Add one implementation task."""

    title: str = Field(min_length=1, max_length=512)
    description: str | None = Field(default=None, max_length=4_000)
    assignee_id: str | None = Field(default=None, max_length=255)


class TaskResponse(BaseModel):
    """One implementation task."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    change_id: UUID
    sequence: int
    title: str
    description: str | None
    assignee_id: str | None
    status: ChangeTaskStatus
    started_at: datetime | None
    completed_at: datetime | None


class ValidationRecordRequest(BaseModel):
    """Record one validation run against a change."""

    kind: ValidationKind
    status: ValidationStatus
    summary: str | None = Field(default=None, max_length=8_000)
    is_gate: bool = False
    ran_by: str | None = Field(default=None, max_length=255)
    evidence: dict[str, Any] = Field(default_factory=dict)


class ValidationResponse(BaseModel):
    """One validation run."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    change_id: UUID
    kind: ValidationKind
    status: ValidationStatus
    summary: str | None
    is_gate: bool
    ran_by: str | None
    ran_at: datetime


class ImplementationResponse(BaseModel):
    """One implementation run."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    change_id: UUID
    status: str
    started_by: str | None
    started_at: datetime | None
    completed_at: datetime | None
    progress_percent: int


# ---- rollback -------------------------------------------------------------------


class RollbackPlanRequest(BaseModel):
    """Prepare a rollback plan."""

    plan: str = Field(min_length=1, max_length=16_000)
    triggered_reason: str = Field(min_length=1, max_length=2_000)
    triggered_by: str | None = Field(default=None, max_length=255)


class RollbackApproveRequest(BaseModel):
    """Approve a planned rollback."""

    approved_by: str = Field(min_length=1, max_length=255)


class RollbackCompleteRequest(BaseModel):
    """Mark a rollback finished."""

    validation_summary: str | None = Field(default=None, max_length=8_000)


class RollbackFailRequest(BaseModel):
    """Mark a rollback attempt failed."""

    reason: str = Field(min_length=1, max_length=2_000)


class RollbackResponse(BaseModel):
    """One rollback."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    change_id: UUID
    status: RollbackStatus
    plan: str
    triggered_by: str | None
    triggered_reason: str
    approved_by: str | None
    approved_at: datetime | None
    started_at: datetime | None
    completed_at: datetime | None
    validation_summary: str | None


# ---- PIR ------------------------------------------------------------------------


class PirStartRequest(BaseModel):
    """Begin a post-implementation review."""

    owner_id: str | None = Field(default=None, max_length=255)


class PirUpdateRequest(BaseModel):
    """Edit a review's content."""

    implementation_summary: str | None = Field(default=None, max_length=16_000)
    objectives_achieved: str | None = Field(default=None, max_length=8_000)
    unexpected_issues: str | None = Field(default=None, max_length=8_000)
    lessons_learned: str | None = Field(default=None, max_length=8_000)
    risk_review: str | None = Field(default=None, max_length=8_000)
    recommendations: str | None = Field(default=None, max_length=8_000)


class PirTransitionRequest(BaseModel):
    """Move a review through its lifecycle."""

    status: PirStatus
    actor_id: str | None = Field(default=None, max_length=255)


class PirActionItemCreateRequest(BaseModel):
    """Commit a follow-up action from a review."""

    title: str = Field(min_length=1, max_length=512)
    description: str | None = Field(default=None, max_length=4_000)
    owner_id: str | None = Field(default=None, max_length=255)
    due_at: datetime | None = None


class PirActionItemResponse(BaseModel):
    """One PIR action item."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    post_review_id: UUID
    title: str
    description: str | None
    status: ChangeTaskStatus
    owner_id: str | None
    due_at: datetime | None
    completed_at: datetime | None


class PirResponse(BaseModel):
    """One post-implementation review."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    change_id: UUID
    status: PirStatus
    owner_id: str | None
    implementation_summary: str | None
    objectives_achieved: str | None
    unexpected_issues: str | None
    lessons_learned: str | None
    risk_review: str | None
    recommendations: str | None
    approved_by: str | None
    approved_at: datetime | None


# ---- statistics, reports, audit --------------------------------------------------


class StatisticsRollupRequest(BaseModel):
    """Compute and store one window's statistics."""

    window_start: datetime
    window_end: datetime


class StatisticResponse(BaseModel):
    """One rolled-up statistics window."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    window_start: datetime
    window_end: datetime
    changes_created: int
    changes_completed: int
    changes_rolled_back: int
    changes_rejected: int
    changes_cancelled: int
    emergency_changes: int
    open_total: int
    success_rate: float
    avg_approval_duration_seconds: float | None
    avg_implementation_duration_seconds: float | None
    conflicts_detected: int
    by_risk_level: dict[str, int]
    by_category: dict[str, int]


class ReportGenerateRequest(BaseModel):
    """Generate a report."""

    kind: ReportKind
    report_format: ReportFormat = ReportFormat.JSON
    title: str | None = Field(default=None, max_length=512)


class ReportResponse(BaseModel):
    """One generated report."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    kind: ReportKind
    report_format: ReportFormat
    title: str
    status: str
    row_count: int
    error: str | None
    generated_at: datetime | None


class AuditEntryResponse(BaseModel):
    """One audit trail entry."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    action: str
    entity_type: str
    entity_id: UUID | None
    entity_reference: str | None
    actor_id: str | None
    occurred_at: datetime
    summary: str
    succeeded: bool


__all__ = [
    "ApprovalDecideRequest",
    "ApprovalDelegateRequest",
    "ApprovalRequestPayload",
    "ApprovalResponse",
    "ApproverPayload",
    "AuditEntryResponse",
    "AvailabilityResponse",
    "CabResponse",
    "CabScheduleRequest",
    "CabVoteRequest",
    "CabVoteResponse",
    "CalendarEntryCreateRequest",
    "CalendarEntryResponse",
    "ChangeCreateRequest",
    "ChangeRelationshipRequest",
    "ChangeRelationshipResponse",
    "ChangeResponse",
    "ChangeScheduleRequest",
    "ChangeUpdateRequest",
    "ConflictResolveRequest",
    "ConflictResponse",
    "ImplementationResponse",
    "PirActionItemCreateRequest",
    "PirActionItemResponse",
    "PirResponse",
    "PirStartRequest",
    "PirTransitionRequest",
    "PirUpdateRequest",
    "ReportGenerateRequest",
    "ReportResponse",
    "RiskAssessRequest",
    "RiskAssessmentResponse",
    "RiskDimensionsPayload",
    "RiskOverrideRequest",
    "RollbackApproveRequest",
    "RollbackCompleteRequest",
    "RollbackFailRequest",
    "RollbackPlanRequest",
    "RollbackResponse",
    "StatisticResponse",
    "StatisticsRollupRequest",
    "TaskCreateRequest",
    "TaskResponse",
    "ValidationRecordRequest",
    "ValidationResponse",
]
