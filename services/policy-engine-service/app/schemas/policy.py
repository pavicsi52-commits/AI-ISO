"""Request and response shapes for the policy engine API.

The HTTP boundary. These deliberately do **not** re-implement the
validation in :mod:`app.rules.engine` or :mod:`app.conditions.operators`
-- whether a condition is usable is decided by the module that owns that
question, at authoring time, with a message naming what is wrong.

**The decision response is the one shape worth reading twice.** It
carries ``permitted`` separately from ``effect``, because
``require_approval`` is neither an allow nor a deny and a caller checking
one boolean must not have obligations quietly filed under permitted.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.models.enums import (
    ActionType,
    ApprovalStatus,
    ApprovalType,
    AttributeSource,
    ComplianceStandard,
    JobStatus,
    LogicalOperator,
    PolicyCategory,
    PolicyEffect,
    PolicyStatus,
    PolicyType,
    QuotaPeriod,
    QuotaScope,
    ReportKind,
    ResourceType,
    RuleOperator,
    SimulationKind,
    SubjectType,
    ViolationStatus,
)

# ---- rules ------------------------------------------------------------


class ConditionPayload(BaseModel):
    """One comparison inside a rule."""

    source: AttributeSource
    path: str = Field(min_length=1, max_length=512)
    operator: RuleOperator
    value: Any = None
    negate: bool = False
    description: str | None = Field(default=None, max_length=1_000)
    value_source: AttributeSource | None = None
    value_path: str | None = Field(default=None, max_length=512)
    """Compare against another attribute rather than a literal.

    The only way to express the central ABAC statement -- "the resource's
    organization must equal the subject's" -- because no literal means
    "whatever the caller's organization happens to be".
    """


class RulePayload(BaseModel):
    """A logical combination of conditions and nested rules."""

    name: str = Field(default="rule", max_length=255)
    logical_operator: LogicalOperator = LogicalOperator.ALL
    conditions: list[ConditionPayload] = Field(default_factory=list)
    children: list[RulePayload] = Field(default_factory=list)
    negate: bool = False
    description: str | None = Field(default=None, max_length=1_000)


RulePayload.model_rebuild()


# ---- policies ---------------------------------------------------------


class PolicyCreateRequest(BaseModel):
    """Author a new policy.

    No ``status`` field, deliberately. A policy that could be created
    already published would let the whole review pipeline be bypassed by
    one extra field on a create call.
    """

    slug: str = Field(min_length=1, max_length=128, pattern=r"^[a-z0-9][a-z0-9-]*$")
    name: str = Field(min_length=1, max_length=255)
    effect: PolicyEffect
    category: PolicyCategory = PolicyCategory.AUTHORIZATION
    policy_type: PolicyType = PolicyType.RBAC
    description: str | None = Field(default=None, max_length=4_000)
    priority: int = Field(default=100, ge=0, le=10_000)
    subject_types: list[SubjectType] = Field(default_factory=list)
    resource_types: list[ResourceType] = Field(default_factory=list)
    actions: list[ActionType] = Field(default_factory=list)
    obligations: dict[str, Any] = Field(default_factory=dict)
    risk_weight: float = Field(default=0.0, ge=0.0, le=1.0)
    tags: list[str] = Field(default_factory=list)


class PolicyUpdateRequest(BaseModel):
    """Change a policy's metadata.

    Every field optional; only what is sent is changed. ``status`` and
    ``compiled_rule`` are absent on purpose -- lifecycle and content move
    through the publish and rollback endpoints, which is where the review
    and the version record happen.
    """

    name: str | None = Field(default=None, min_length=1, max_length=255)
    description: str | None = Field(default=None, max_length=4_000)
    category: PolicyCategory | None = None
    policy_type: PolicyType | None = None
    effect: PolicyEffect | None = None
    priority: int | None = Field(default=None, ge=0, le=10_000)
    subject_types: list[SubjectType] | None = None
    resource_types: list[ResourceType] | None = None
    actions: list[ActionType] | None = None
    obligations: dict[str, Any] | None = None
    risk_weight: float | None = Field(default=None, ge=0.0, le=1.0)
    tags: list[str] | None = None


class PolicyResponse(BaseModel):
    """One policy as returned."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    slug: str
    name: str
    description: str | None
    category: PolicyCategory
    policy_type: PolicyType
    effect: PolicyEffect
    status: PolicyStatus
    priority: int
    version: str
    subject_types: list[str]
    resource_types: list[str]
    actions: list[str]
    obligations: dict[str, Any]
    risk_weight: float
    tags: list[str]
    is_system: bool
    evaluation_count: int
    published_at: datetime | None


class PolicyVersionResponse(BaseModel):
    """One published version."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    policy_id: UUID
    sequence: int
    version: str
    name: str
    effect: PolicyEffect
    priority: int
    change_summary: str | None
    published_at: datetime | None
    checksum_sha256: str | None


class RuleTreeRequest(BaseModel):
    """Replace a policy's authored rules."""

    rule: RulePayload


class PublishRequest(BaseModel):
    """Compile and make a policy live."""

    change_summary: str | None = Field(default=None, max_length=2_000)
    breaking: bool = False
    feature: bool = False
    """Which part of the semantic version to advance.

    Both false means a patch. Named rather than inferred, because
    "did this change break anybody?" is a judgement the author has and
    the diff does not.
    """


class RollbackRequest(BaseModel):
    """Restore a previously published version."""

    version: str | None = Field(default=None, max_length=32)
    """Which version to restore. Omitted means the one before current."""


class TransitionRequest(BaseModel):
    """Move a policy through its lifecycle."""

    target: PolicyStatus


# ---- evaluation -------------------------------------------------------


class EvaluationContextPayload(BaseModel):
    """The attributes one decision may see."""

    subject: dict[str, Any] = Field(default_factory=dict)
    resource: dict[str, Any] = Field(default_factory=dict)
    action: dict[str, Any] = Field(default_factory=dict)
    context: dict[str, Any] = Field(default_factory=dict)
    environment: dict[str, Any] = Field(default_factory=dict)
    organization: dict[str, Any] = Field(default_factory=dict)
    project: dict[str, Any] = Field(default_factory=dict)
    custom: dict[str, Any] = Field(default_factory=dict)


class EvaluateRequest(BaseModel):
    """Ask whether one operation is permitted."""

    subject_type: SubjectType = SubjectType.USER
    subject_id: str = Field(min_length=1, max_length=255)
    resource_type: ResourceType
    action: ActionType
    resource_id: str | None = Field(default=None, max_length=255)
    project_id: str | None = Field(default=None, max_length=64)
    request_id: str | None = Field(default=None, max_length=64)
    attributes: EvaluationContextPayload = Field(default_factory=EvaluationContextPayload)
    quota_amount: float = Field(default=1.0, ge=0.0)
    quota_resource: str | None = Field(default=None, max_length=128)
    record: bool = True
    """Whether to store the decision.

    A caller checking speculatively -- "could I do this?" -- sets this
    false so a dry run does not pollute the decision log or the
    statistics derived from it.
    """

    consume_quota: bool = True


class DecisionResponse(BaseModel):
    """One authorization answer."""

    effect: PolicyEffect
    permitted: bool
    """Whether the caller may proceed **now**.

    Separate from ``effect`` because ``require_approval`` is neither an
    allow nor a deny. A client checking one boolean must not have
    obligations quietly filed under permitted -- that is how an approval
    gate stops existing.
    """

    denied: bool
    reason: str
    deciding_policy_id: str | None = None
    matched_policy_ids: list[str] = Field(default_factory=list)
    risk_score: float = 0.0
    obligations: dict[str, Any] = Field(default_factory=dict)
    duration_ms: float = 0.0
    policies_considered: int = 0
    errors: list[str] = Field(default_factory=list)
    trace: list[dict[str, Any]] = Field(default_factory=list)
    decision_id: str | None = None


class StoredDecisionResponse(BaseModel):
    """One recorded decision."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    request_id: str | None
    subject_type: SubjectType
    subject_id: str
    resource_type: ResourceType
    resource_id: str | None
    action: ActionType
    effect: PolicyEffect
    permitted: bool
    reason: str
    risk_score: float
    duration_ms: float
    policies_considered: int
    decided_at: datetime


# ---- simulation -------------------------------------------------------


class SimulationRequestPayload(BaseModel):
    """One request to rehearse."""

    label: str | None = Field(default=None, max_length=255)
    subject_type: SubjectType = SubjectType.USER
    resource_type: ResourceType
    action: ActionType
    subject: dict[str, Any] = Field(default_factory=dict)
    resource: dict[str, Any] = Field(default_factory=dict)
    action_attributes: dict[str, Any] = Field(default_factory=dict)
    context: dict[str, Any] = Field(default_factory=dict)
    environment: dict[str, Any] = Field(default_factory=dict)
    organization: dict[str, Any] = Field(default_factory=dict)
    project: dict[str, Any] = Field(default_factory=dict)
    custom: dict[str, Any] = Field(default_factory=dict)


class SimulateRequest(BaseModel):
    """Rehearse a catalogue change."""

    label: str = Field(default="simulation", max_length=255)
    kind: SimulationKind = SimulationKind.WHAT_IF
    requests: list[SimulationRequestPayload] = Field(default_factory=list)
    draft_policy_ids: list[UUID] = Field(default_factory=list)
    excluded_policy_ids: list[UUID] = Field(default_factory=list)
    """Policies to leave out, which is how "what breaks if I retire this?"
    gets asked -- the mirror of the more obvious question."""

    store: bool = True


class SimulationResponse(BaseModel):
    """One stored simulation."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    label: str
    kind: SimulationKind
    status: JobStatus
    request_count: int
    allowed_count: int
    denied_count: int
    changed_count: int
    summary: str | None
    conflicts: list[Any]
    duration_ms: float
    started_at: datetime
    finished_at: datetime | None
    error: str | None


# ---- approvals --------------------------------------------------------


class ApprovalDecisionRequest(BaseModel):
    """Record one approver's answer."""

    approver_id: str = Field(min_length=1, max_length=255)
    approved: bool
    comment: str = Field(default="", max_length=2_000)
    approver_roles: list[str] = Field(default_factory=list)


class ApprovalResponse(BaseModel):
    """One approval obligation."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    approval_type: ApprovalType
    status: ApprovalStatus
    subject_id: str
    resource_type: ResourceType
    resource_id: str | None
    action: ActionType
    required_levels: int
    required_roles: list[str]
    decisions: list[Any]
    is_emergency: bool
    reason: str | None
    requested_at: datetime
    expires_at: datetime
    resolved_at: datetime | None


# ---- quotas -----------------------------------------------------------


class QuotaCreateRequest(BaseModel):
    """Define a consumption budget."""

    scope: QuotaScope
    scope_id: str = Field(default="", max_length=255)
    resource: str = Field(default="requests", min_length=1, max_length=128)
    limit_value: float = Field(ge=0.0)
    """Zero means unlimited, not "nothing allowed".

    Deliberate: a budget created without a limit would otherwise refuse
    every request for that resource, and an accidental total outage is
    far worse than an accidental absence of enforcement.
    """

    period: QuotaPeriod = QuotaPeriod.MONTHLY
    is_hard_limit: bool = True
    description: str | None = Field(default=None, max_length=1_000)


class QuotaUpdateRequest(BaseModel):
    """Change a budget's ceiling or hardness."""

    limit_value: float | None = Field(default=None, ge=0.0)
    is_hard_limit: bool | None = None


class QuotaResponse(BaseModel):
    """One consumption budget."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    scope: QuotaScope
    scope_id: str
    resource: str
    limit_value: float
    consumed: float
    period: QuotaPeriod
    period_started_at: datetime
    is_hard_limit: bool
    exceeded_count: int
    description: str | None


# ---- violations and exceptions ----------------------------------------


class ViolationResponse(BaseModel):
    """One recorded breach."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    policy_id: UUID | None
    title: str
    description: str | None
    standard: ComplianceStandard
    severity: str
    status: ViolationStatus
    subject_id: str | None
    resource_id: str | None
    detected_at: datetime
    resolved_at: datetime | None
    resolution_note: str | None


class ViolationResolveRequest(BaseModel):
    """Close a violation."""

    note: str = Field(min_length=1, max_length=4_000)
    """Required. A violation closed without a stated reason is
    indistinguishable from one somebody clicked past."""

    waived: bool = False


class ExceptionCreateRequest(BaseModel):
    """Waive one policy, for a bounded time and scope."""

    policy_id: UUID
    reason: str = Field(min_length=1, max_length=4_000)
    expires_at: datetime
    """Required, and bounded by the service. A permanent exception is not
    an exception -- it is an undocumented policy change."""

    subject_type: SubjectType | None = None
    subject_id: str | None = Field(default=None, max_length=255)
    resource_type: ResourceType | None = None
    resource_id: str | None = Field(default=None, max_length=255)


class ExceptionResponse(BaseModel):
    """One waiver."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    policy_id: UUID
    reason: str
    subject_id: str | None
    resource_id: str | None
    granted_at: datetime
    expires_at: datetime
    revoked_at: datetime | None
    use_count: int


# ---- operations -------------------------------------------------------


class StatisticsResponse(BaseModel):
    """An organization's policy analytics."""

    model_config = ConfigDict(from_attributes=True)

    policy_count: int
    published_count: int
    draft_count: int
    decision_count: int
    allowed_count: int
    denied_count: int
    approval_required_count: int
    violation_count: int
    open_violation_count: int
    quota_violation_count: int
    pending_approval_count: int
    expired_approval_count: int
    average_latency_ms: float
    p95_latency_ms: float
    unused_policy_count: int
    policy_usage: dict[str, Any]
    decisions_by_effect: dict[str, Any]
    decisions_by_category: dict[str, Any]
    computed_at: datetime


class ReportCreateRequest(BaseModel):
    """Generate a report."""

    kind: ReportKind
    title: str | None = Field(default=None, max_length=255)
    parameters: dict[str, Any] = Field(default_factory=dict)


class ReportResponse(BaseModel):
    """One generated report."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    title: str
    kind: ReportKind
    status: JobStatus
    summary: str | None
    size_bytes: int
    checksum_sha256: str | None
    generated_at: datetime
    duration_ms: float
    error: str | None


class AuditEntryResponse(BaseModel):
    """One audit entry."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    action: str
    outcome: str
    entity_type: str
    entity_id: str | None
    actor_id: UUID | None
    reason: str | None
    occurred_at: datetime


__all__ = [
    "ApprovalDecisionRequest",
    "ApprovalResponse",
    "AuditEntryResponse",
    "ConditionPayload",
    "DecisionResponse",
    "EvaluateRequest",
    "EvaluationContextPayload",
    "ExceptionCreateRequest",
    "ExceptionResponse",
    "PolicyCreateRequest",
    "PolicyResponse",
    "PolicyUpdateRequest",
    "PolicyVersionResponse",
    "PublishRequest",
    "QuotaCreateRequest",
    "QuotaResponse",
    "QuotaUpdateRequest",
    "ReportCreateRequest",
    "ReportResponse",
    "RollbackRequest",
    "RulePayload",
    "RuleTreeRequest",
    "SimulateRequest",
    "SimulationRequestPayload",
    "SimulationResponse",
    "StatisticsResponse",
    "StoredDecisionResponse",
    "TransitionRequest",
    "ViolationResolveRequest",
    "ViolationResponse",
]
