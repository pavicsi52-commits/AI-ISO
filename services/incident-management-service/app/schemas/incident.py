"""Request and response shapes for the incident management API.

Bounded everywhere: every string has a max length and every list a max
size. This service accepts incidents from monitoring, alerting,
webhooks, and email -- automated callers whose payloads this service
does not control the shape of, and the ceiling that is not stated is
the one somebody eventually exceeds.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.models.enums import (
    ActionItemStatus,
    AssignmentMethod,
    EscalationStatus,
    ImpactLevel,
    IncidentCategory,
    IncidentPriority,
    IncidentSource,
    IncidentStatus,
    PostmortemStatus,
    ProblemStatus,
    RcaMethod,
    ReportFormat,
    ReportKind,
    RiskLevel,
    SlaKind,
    SlaStatus,
    TimelineEventKind,
    WarRoomRole,
    WarRoomStatus,
)

MAX_TAGS = 50
MAX_STAKEHOLDERS = 200
MAX_SERVICES_PER_ASSESSMENT = 500


# ---- incidents ----------------------------------------------------------


class IncidentCreateRequest(BaseModel):
    """Open a new incident."""

    title: str = Field(min_length=1, max_length=512)
    description: str | None = Field(default=None, max_length=8_000)
    source: IncidentSource = IncidentSource.MANUAL
    source_reference: str | None = Field(default=None, max_length=512)
    category: IncidentCategory = IncidentCategory.CUSTOM
    priority: IncidentPriority = IncidentPriority.P3_MEDIUM
    correlation_key: str | None = Field(default=None, max_length=512)
    tags: list[str] = Field(default_factory=list, max_length=MAX_TAGS)


class IncidentTransitionRequest(BaseModel):
    """Move an incident through its lifecycle."""

    status: IncidentStatus
    note: str | None = Field(default=None, max_length=4_000)


class IncidentAssignRequest(BaseModel):
    """Assign an incident directly to a named responder."""

    assignee_id: str = Field(min_length=1, max_length=255)
    assignee_team: str | None = Field(default=None, max_length=255)
    method: AssignmentMethod = AssignmentMethod.MANUAL
    reason: str | None = Field(default=None, max_length=1_000)


class ResponderPayload(BaseModel):
    """One candidate on a roster for automatic assignment."""

    responder_id: str = Field(min_length=1, max_length=255)
    team: str | None = Field(default=None, max_length=255)
    skills: list[str] = Field(default_factory=list, max_length=MAX_TAGS)
    is_on_call: bool = False
    is_available: bool = True


class IncidentAutoAssignRequest(BaseModel):
    """Assign an incident by choosing from a supplied roster."""

    roster: list[ResponderPayload] = Field(min_length=1, max_length=500)
    required_skills: list[str] = Field(default_factory=list, max_length=MAX_TAGS)
    prefer_on_call: bool = True


class IncidentMergeRequest(BaseModel):
    """Merge one incident into another."""

    target_incident_id: UUID
    reason: str = Field(min_length=1, max_length=2_000)


class WorklogCreateRequest(BaseModel):
    """Record effort spent on an incident."""

    note: str = Field(min_length=1, max_length=4_000)
    kind: str = Field(default="other", max_length=32)
    minutes_spent: int | None = Field(default=None, ge=0, le=100_000)


class TimelineNoteRequest(BaseModel):
    """Add a free-text note to an incident's timeline."""

    summary: str = Field(min_length=1, max_length=4_000)


class IncidentResponse(BaseModel):
    """One incident."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    reference: str
    title: str
    description: str | None
    source: str
    source_reference: str | None
    category: str
    priority: str
    status: str
    fingerprint: str | None
    assignee_id: str | None
    assignee_team: str | None
    assignment_method: str | None
    risk_level: str
    is_major: bool
    merged_into_id: UUID | None
    problem_id: UUID | None
    root_cause_id: UUID | None
    detected_at: datetime
    responded_at: datetime | None
    acknowledged_at: datetime | None
    resolved_at: datetime | None
    closed_at: datetime | None
    mtta_seconds: float | None
    mttr_seconds: float | None
    reopen_count: int
    escalation_count: int
    tags: list[str]
    created_at: datetime
    updated_at: datetime


class TimelineEntryResponse(BaseModel):
    """One timeline entry."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    kind: TimelineEventKind
    summary: str
    actor_id: str | None
    occurred_at: datetime
    details: dict[str, Any]


class WorklogResponse(BaseModel):
    """One worklog entry."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    kind: str
    author_id: str | None
    note: str
    minutes_spent: int | None
    logged_at: datetime


# ---- sla ------------------------------------------------------------------


class SlaResponse(BaseModel):
    """One SLA clock."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    incident_id: UUID
    kind: SlaKind
    status: SlaStatus
    target_minutes: int
    is_24x7: bool
    started_at: datetime | None
    due_at: datetime | None
    paused_at: datetime | None
    paused_seconds_total: float
    met_at: datetime | None
    breached_at: datetime | None
    warning_sent_at: datetime | None


class SlaPauseRequest(BaseModel):
    """Pause a running SLA clock."""

    reason: str = Field(min_length=1, max_length=1_000)


# ---- escalation -------------------------------------------------------------


class EscalationResponse(BaseModel):
    """One escalation."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    incident_id: UUID
    trigger: str
    status: EscalationStatus
    level: int
    escalate_to_id: str | None
    escalate_to_role: str | None
    reason: str
    triggered_at: datetime | None
    acknowledged_at: datetime | None


class ManualEscalationRequest(BaseModel):
    """Escalate an incident to a named target, outside any policy ladder."""

    target_id: str = Field(min_length=1, max_length=255)
    reason: str = Field(min_length=1, max_length=2_000)


class EscalationCancelRequest(BaseModel):
    """Cancel a pending or triggered escalation."""

    reason: str = Field(min_length=1, max_length=1_000)


# ---- impact -----------------------------------------------------------------


class ServiceImpactPayload(BaseModel):
    """One affected service."""

    service_name: str = Field(min_length=1, max_length=255)
    impact_level: ImpactLevel = ImpactLevel.MODERATE
    is_root: bool = False


class AssetImpactPayload(BaseModel):
    """One affected asset."""

    asset_id: str | None = Field(default=None, max_length=255)
    asset_name: str = Field(min_length=1, max_length=255)
    impact_level: ImpactLevel = ImpactLevel.MODERATE
    detail: str | None = Field(default=None, max_length=2_000)


class ImpactAssessRequest(BaseModel):
    """Record a fresh impact assessment."""

    services: list[ServiceImpactPayload] = Field(
        default_factory=list, max_length=MAX_SERVICES_PER_ASSESSMENT
    )
    assets: list[AssetImpactPayload] = Field(
        default_factory=list, max_length=MAX_SERVICES_PER_ASSESSMENT
    )
    business_impact: ImpactLevel = ImpactLevel.NONE
    customer_impact: ImpactLevel = ImpactLevel.NONE
    affected_users_estimate: int | None = Field(default=None, ge=0)
    assessed_by: str | None = Field(default=None, max_length=255)


class ImpactResponse(BaseModel):
    """One impact assessment."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    incident_id: UUID
    business_impact: ImpactLevel
    customer_impact: ImpactLevel
    topology_impact: ImpactLevel
    risk_level: RiskLevel
    affected_users_estimate: int | None
    revenue_impact_estimate: float | None
    blast_radius_summary: str | None
    assessed_by: str | None
    assessed_at: datetime


# ---- major incidents and war rooms ----------------------------------------


class MajorIncidentDeclareRequest(BaseModel):
    """Declare an incident major."""

    reason: str = Field(min_length=1, max_length=4_000)
    incident_commander_id: str | None = Field(default=None, max_length=255)
    stakeholder_ids: list[str] = Field(default_factory=list, max_length=MAX_STAKEHOLDERS)


class MajorIncidentResponse(BaseModel):
    """One major incident declaration."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    incident_id: UUID
    declared_by: str | None
    declared_at: datetime
    declaration_reason: str
    incident_commander_id: str | None
    communication_lead_id: str | None
    technical_lead_id: str | None
    business_lead_id: str | None
    executive_summary: str | None
    last_status_update_at: datetime | None
    stood_down_at: datetime | None
    stood_down_by: str | None
    closure_approved_by: str | None
    closure_approved_at: datetime | None
    stakeholder_ids: list[str]


class MajorIncidentStatusUpdateRequest(BaseModel):
    """Record a stakeholder status update."""

    summary: str = Field(min_length=1, max_length=4_000)


class MajorIncidentApproveClosureRequest(BaseModel):
    """Approve closing out a major incident."""

    approved_by: str = Field(min_length=1, max_length=255)


class WarRoomResponse(BaseModel):
    """One war room."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    incident_id: UUID
    major_incident_id: UUID | None
    status: WarRoomStatus
    opened_by: str | None
    opened_at: datetime
    closed_at: datetime | None
    shared_notes: str | None
    recording_reference: str | None


class WarRoomRoleRequest(BaseModel):
    """Add a participant to a war room."""

    participant_id: str = Field(min_length=1, max_length=255)
    role: WarRoomRole = WarRoomRole.PARTICIPANT


class WarRoomLeaveRequest(BaseModel):
    """Mark a participant as having left."""

    participant_id: str = Field(min_length=1, max_length=255)


class WarRoomNoteRequest(BaseModel):
    """Append to a war room's shared notes."""

    note: str = Field(min_length=1, max_length=8_000)


class WarRoomParticipantResponse(BaseModel):
    """One war room participant."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    participant_id: str
    role: WarRoomRole
    joined_at: datetime
    left_at: datetime | None


# ---- root cause, problems, known errors -----------------------------------


class RootCauseRecordRequest(BaseModel):
    """Record a root cause finding."""

    method: RcaMethod
    summary: str = Field(min_length=1, max_length=8_000)
    contributing_factors: list[str] = Field(default_factory=list, max_length=MAX_TAGS)
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)
    is_confirmed: bool = False
    evidence: dict[str, Any] = Field(default_factory=dict)
    recorded_by: str | None = Field(default=None, max_length=255)


class RootCauseConfirmRequest(BaseModel):
    """Confirm a root cause finding."""

    confirmed_by: str = Field(min_length=1, max_length=255)


class RootCauseResponse(BaseModel):
    """One root cause finding."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    incident_id: UUID
    method: RcaMethod
    summary: str
    contributing_factors: list[str]
    confidence: float
    is_confirmed: bool
    confirmed_by: str | None
    recorded_by: str | None
    recorded_at: datetime


class ProblemCreateRequest(BaseModel):
    """Record a recurring pattern as a problem."""

    title: str = Field(min_length=1, max_length=512)
    description: str | None = Field(default=None, max_length=8_000)
    incident_ids: list[UUID] = Field(default_factory=list, max_length=1_000)
    owner_id: str | None = Field(default=None, max_length=255)


class ProblemTransitionRequest(BaseModel):
    """Move a problem through its lifecycle."""

    status: ProblemStatus
    permanent_fix: str | None = Field(default=None, max_length=8_000)


class ProblemLinkIncidentRequest(BaseModel):
    """Attach one more incident to an existing problem."""

    incident_id: UUID


class ProblemResponse(BaseModel):
    """One problem record."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    reference: str
    title: str
    description: str | None
    status: ProblemStatus
    incident_ids: list[str]
    incident_count: int
    owner_id: str | None
    permanent_fix: str | None
    identified_at: datetime
    resolved_at: datetime | None
    closed_at: datetime | None


class KnownErrorCreateRequest(BaseModel):
    """Record a known error against a problem."""

    title: str = Field(min_length=1, max_length=512)
    root_cause_summary: str = Field(min_length=1, max_length=8_000)
    workaround: str | None = Field(default=None, max_length=8_000)
    affected_versions: list[str] = Field(default_factory=list, max_length=MAX_TAGS)
    recorded_by: str | None = Field(default=None, max_length=255)


class KnownErrorResponse(BaseModel):
    """One known error."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    problem_id: UUID
    title: str
    root_cause_summary: str
    workaround: str | None
    affected_versions: list[str]
    is_active: bool
    recorded_by: str | None
    recorded_at: datetime
    retired_at: datetime | None


# ---- postmortems ------------------------------------------------------------


class PostmortemStartRequest(BaseModel):
    """Begin a postmortem for an incident."""

    author_id: str | None = Field(default=None, max_length=255)


class PostmortemUpdateRequest(BaseModel):
    """Edit a postmortem's content."""

    executive_summary: str | None = Field(default=None, max_length=8_000)
    timeline_summary: str | None = Field(default=None, max_length=8_000)
    root_cause_summary: str | None = Field(default=None, max_length=8_000)
    impact_summary: str | None = Field(default=None, max_length=8_000)
    lessons_learned: str | None = Field(default=None, max_length=8_000)


class PostmortemTransitionRequest(BaseModel):
    """Move a postmortem through its lifecycle."""

    status: PostmortemStatus
    actor_id: str | None = Field(default=None, max_length=255)


class PostmortemResponse(BaseModel):
    """One postmortem."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    incident_id: UUID
    status: PostmortemStatus
    executive_summary: str | None
    timeline_summary: str | None
    root_cause_summary: str | None
    impact_summary: str | None
    lessons_learned: str | None
    is_blameless: bool
    author_id: str | None
    approved_by: str | None
    approved_at: datetime | None
    published_at: datetime | None


class ActionItemCreateRequest(BaseModel):
    """Commit a follow-up action from a postmortem."""

    title: str = Field(min_length=1, max_length=512)
    description: str | None = Field(default=None, max_length=4_000)
    owner_id: str | None = Field(default=None, max_length=255)
    due_at: datetime | None = None


class ActionItemResponse(BaseModel):
    """One postmortem action item."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    postmortem_id: UUID
    title: str
    description: str | None
    status: ActionItemStatus
    owner_id: str | None
    due_at: datetime | None
    completed_at: datetime | None
    verified_at: datetime | None


# ---- reports and audit -------------------------------------------------------


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
    incidents_created: int
    incidents_resolved: int
    incidents_closed: int
    incidents_reopened: int
    major_incidents: int
    open_total: int
    avg_mtta_seconds: float | None
    avg_mttr_seconds: float | None
    p90_mttr_seconds: float | None
    sla_met_count: int
    sla_breached_count: int
    sla_compliance_rate: float
    escalations_triggered: int
    by_category: dict[str, int]
    by_priority: dict[str, int]


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
    "ActionItemCreateRequest",
    "ActionItemResponse",
    "AssetImpactPayload",
    "AuditEntryResponse",
    "EscalationCancelRequest",
    "EscalationResponse",
    "ImpactAssessRequest",
    "ImpactResponse",
    "IncidentAssignRequest",
    "IncidentAutoAssignRequest",
    "IncidentCreateRequest",
    "IncidentMergeRequest",
    "IncidentResponse",
    "IncidentTransitionRequest",
    "KnownErrorCreateRequest",
    "KnownErrorResponse",
    "MajorIncidentApproveClosureRequest",
    "MajorIncidentDeclareRequest",
    "MajorIncidentResponse",
    "MajorIncidentStatusUpdateRequest",
    "ManualEscalationRequest",
    "PostmortemResponse",
    "PostmortemStartRequest",
    "PostmortemTransitionRequest",
    "PostmortemUpdateRequest",
    "ProblemCreateRequest",
    "ProblemLinkIncidentRequest",
    "ProblemResponse",
    "ProblemTransitionRequest",
    "ReportGenerateRequest",
    "ReportResponse",
    "ResponderPayload",
    "RootCauseConfirmRequest",
    "RootCauseRecordRequest",
    "RootCauseResponse",
    "ServiceImpactPayload",
    "SlaPauseRequest",
    "SlaResponse",
    "StatisticResponse",
    "StatisticsRollupRequest",
    "TimelineEntryResponse",
    "TimelineNoteRequest",
    "WarRoomLeaveRequest",
    "WarRoomNoteRequest",
    "WarRoomParticipantResponse",
    "WarRoomResponse",
    "WarRoomRoleRequest",
    "WorklogCreateRequest",
    "WorklogResponse",
]
