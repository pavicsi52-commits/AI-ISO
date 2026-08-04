"""The platform's fixed change-management vocabulary (docs/053).

Every ``Mapped[SomeEnum]`` column below is backed by ``String`` at the
database layer, per this repository's established SQLAlchemy 2.0
pattern: a raw string round-trips through Postgres exactly, unlike a
native ``ENUM`` type, which turns every new member into a migration
against a type the whole cluster shares. The cost is that a value freshly
loaded from the database is a plain ``str``, not the enum member -- so
every column that is ever compared, branched on, or handed to another
enum-typed field carries an ``X_of()`` normaliser here, and application
code calls it on the *column*, never on the record that owns it.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Final


class ChangeType(StrEnum):
    """The process a change follows -- what it *is procedurally*.

    Distinct from :class:`ChangeCategory`, which is what a change
    touches. A database change and an infrastructure change can both be
    Normal changes; the type governs the approval path, not the domain.
    """

    STANDARD = "standard"
    """Pre-approved, low-risk, and repeatable. Never needs its own CAB
    review -- that is what made it eligible to be a standard change in
    the first place."""

    NORMAL = "normal"
    """The default path: risk assessment, approval, and (for anything
    above low risk) CAB review before scheduling."""

    EMERGENCY = "emergency"
    """May implement before approval completes when the alternative is
    an ongoing incident, but never without an approval existing at
    all -- see ``ChangeService.record_emergency_approval``."""

    EXPEDITED = "expedited"
    """Normal's approval chain, compressed rather than skipped."""


class ChangeCategory(StrEnum):
    """What a change touches -- the domain, not the process."""

    INFRASTRUCTURE = "infrastructure"
    APPLICATION = "application"
    CONFIGURATION = "configuration"
    DATABASE = "database"
    CLOUD = "cloud"
    KUBERNETES = "kubernetes"
    SECURITY = "security"
    INDUSTRIAL = "industrial"
    CUSTOM = "custom"


class ChangePriority(StrEnum):
    """How urgently a change needs to move through its lifecycle."""

    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    PLANNING = "planning"


class ChangeStatus(StrEnum):
    """Where a change stands in its lifecycle.

    The full ITIL-aligned path docs/053 names. ``app/changes/engine.py``
    owns which moves between these are legal; this enum only fixes the
    vocabulary.
    """

    DRAFT = "draft"
    SUBMITTED = "submitted"
    RISK_ASSESSMENT = "risk_assessment"
    PENDING_APPROVAL = "pending_approval"
    CAB_REVIEW = "cab_review"
    SCHEDULED = "scheduled"
    READY = "ready"
    IN_PROGRESS = "in_progress"
    VALIDATION = "validation"
    COMPLETED = "completed"
    ROLLED_BACK = "rolled_back"
    CANCELLED = "cancelled"
    REJECTED = "rejected"
    CLOSED = "closed"


class RiskLevel(StrEnum):
    """A change's overall risk banding, derived -- never entered directly."""

    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class RiskLikelihood(StrEnum):
    """How likely a change is to cause a problem, on a published 5-point scale."""

    RARE = "rare"
    UNLIKELY = "unlikely"
    POSSIBLE = "possible"
    LIKELY = "likely"
    ALMOST_CERTAIN = "almost_certain"


class RiskImpact(StrEnum):
    """How bad it would be if a change did cause a problem."""

    MINIMAL = "minimal"
    MINOR = "minor"
    MODERATE = "moderate"
    MAJOR = "major"
    SEVERE = "severe"


class ApprovalStatus(StrEnum):
    """One approver's decision on one change."""

    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    CONDITIONAL = "conditional"
    DELEGATED = "delegated"
    EXPIRED = "expired"


class ApprovalPolicy(StrEnum):
    """How many approvers, and which ones, a change's approval requires."""

    SINGLE = "single"
    MULTI_LEVEL = "multi_level"
    ROLE_BASED = "role_based"
    RISK_BASED = "risk_based"


class CabMeetingStatus(StrEnum):
    """A CAB meeting's own lifecycle."""

    SCHEDULED = "scheduled"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    CANCELLED = "cancelled"


class CabVote(StrEnum):
    """One CAB member's vote on one change, at one meeting."""

    APPROVE = "approve"
    REJECT = "reject"
    CONDITIONAL = "conditional"
    ABSTAIN = "abstain"


class CalendarEntryKind(StrEnum):
    """What a change-calendar entry represents."""

    MAINTENANCE_WINDOW = "maintenance_window"
    BLACKOUT_PERIOD = "blackout_period"


class RecurrenceKind(StrEnum):
    """How a calendar entry repeats, if at all."""

    NONE = "none"
    DAILY = "daily"
    WEEKLY = "weekly"
    MONTHLY = "monthly"


class ConflictKind(StrEnum):
    """What two changes are colliding over."""

    OVERLAPPING_MAINTENANCE = "overlapping_maintenance"
    ASSET = "asset"
    SERVICE = "service"
    APPLICATION = "application"
    DEPENDENCY = "dependency"
    RESOURCE = "resource"
    SCHEDULE = "schedule"
    CAB = "cab"


class ConflictStatus(StrEnum):
    """A detected conflict's own lifecycle."""

    DETECTED = "detected"
    ACKNOWLEDGED = "acknowledged"
    RESOLVED = "resolved"
    IGNORED = "ignored"


class ChangeTaskStatus(StrEnum):
    """One implementation task's lifecycle."""

    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"
    BLOCKED = "blocked"


class ImplementationStatus(StrEnum):
    """A change's implementation run, as a whole."""

    NOT_STARTED = "not_started"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"
    PARTIALLY_COMPLETED = "partially_completed"


class ValidationKind(StrEnum):
    """What stage of a change a validation run checks."""

    PRE_CHANGE = "pre_change"
    POST_CHANGE = "post_change"
    CONFIGURATION = "configuration"
    HEALTH = "health"
    COMPLIANCE = "compliance"


class ValidationStatus(StrEnum):
    """One validation run's outcome."""

    PENDING = "pending"
    PASSED = "passed"
    FAILED = "failed"
    SKIPPED = "skipped"


class RollbackStatus(StrEnum):
    """A change's rollback, if one was needed."""

    NOT_REQUIRED = "not_required"
    PLANNED = "planned"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"


class PirStatus(StrEnum):
    """A post-implementation review's lifecycle."""

    DRAFT = "draft"
    IN_REVIEW = "in_review"
    APPROVED = "approved"


class RelationshipKind(StrEnum):
    """How two changes relate to each other."""

    DEPENDS_ON = "depends_on"
    BLOCKS = "blocks"
    RELATED_TO = "related_to"
    SUPERSEDES = "supersedes"
    PART_OF = "part_of"


class ReportKind(StrEnum):
    """Which report a request wants."""

    CHANGE = "change"
    EXECUTIVE = "executive"
    CAB = "cab"
    RISK = "risk"
    CALENDAR = "calendar"
    IMPLEMENTATION = "implementation"
    PIR = "pir"
    COMPLIANCE = "compliance"


class ReportFormat(StrEnum):
    """How a report is rendered."""

    JSON = "json"
    CSV = "csv"
    MARKDOWN = "markdown"


class JobStatus(StrEnum):
    """A background job's lifecycle -- a generated report, here."""

    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class AuditAction(StrEnum):
    """What an audit row records."""

    CHANGE_CREATED = "change_created"
    CHANGE_UPDATED = "change_updated"
    CHANGE_SUBMITTED = "change_submitted"
    RISK_ASSESSED = "risk_assessed"
    APPROVAL_DECIDED = "approval_decided"
    CAB_DECIDED = "cab_decided"
    CHANGE_SCHEDULED = "change_scheduled"
    IMPLEMENTATION_STARTED = "implementation_started"
    IMPLEMENTATION_COMPLETED = "implementation_completed"
    VALIDATION_RECORDED = "validation_recorded"
    ROLLBACK_STARTED = "rollback_started"
    ROLLBACK_COMPLETED = "rollback_completed"
    PIR_COMPLETED = "pir_completed"
    REPORT_GENERATED = "report_generated"
    ADMINISTRATIVE = "administrative"


# ---- weightings and derivations ----------------------------------------

PRIORITY_ORDER: Final[dict[ChangePriority, int]] = {
    ChangePriority.CRITICAL: 0,
    ChangePriority.HIGH: 1,
    ChangePriority.MEDIUM: 2,
    ChangePriority.LOW: 3,
    ChangePriority.PLANNING: 4,
}
"""Lower sorts first, so "more urgent" is always "numerically smaller"
without an off-by-one anyone has to remember."""

RISK_ORDER: Final[dict[RiskLevel, int]] = {
    RiskLevel.LOW: 0,
    RiskLevel.MEDIUM: 1,
    RiskLevel.HIGH: 2,
    RiskLevel.CRITICAL: 3,
}
"""Higher is worse, matching how :func:`app.risk.engine.risk_level_for`
compares two bandings."""

LIKELIHOOD_ORDER: Final[dict[RiskLikelihood, int]] = {
    RiskLikelihood.RARE: 0,
    RiskLikelihood.UNLIKELY: 1,
    RiskLikelihood.POSSIBLE: 2,
    RiskLikelihood.LIKELY: 3,
    RiskLikelihood.ALMOST_CERTAIN: 4,
}

IMPACT_ORDER: Final[dict[RiskImpact, int]] = {
    RiskImpact.MINIMAL: 0,
    RiskImpact.MINOR: 1,
    RiskImpact.MODERATE: 2,
    RiskImpact.MAJOR: 3,
    RiskImpact.SEVERE: 4,
}

OPEN_CHANGE_STATUSES: Final[frozenset[ChangeStatus]] = frozenset(
    {
        ChangeStatus.DRAFT,
        ChangeStatus.SUBMITTED,
        ChangeStatus.RISK_ASSESSMENT,
        ChangeStatus.PENDING_APPROVAL,
        ChangeStatus.CAB_REVIEW,
        ChangeStatus.SCHEDULED,
        ChangeStatus.READY,
        ChangeStatus.IN_PROGRESS,
        ChangeStatus.VALIDATION,
    }
)
"""Statuses that count as "still open" for dashboards and load. A
completed, rolled-back, cancelled, rejected, or closed change is done,
even though not every one of those is a success."""

TERMINAL_CHANGE_STATUSES: Final[frozenset[ChangeStatus]] = frozenset(
    {
        ChangeStatus.COMPLETED,
        ChangeStatus.ROLLED_BACK,
        ChangeStatus.CANCELLED,
        ChangeStatus.REJECTED,
        ChangeStatus.CLOSED,
    }
)

HIGH_RISK_LEVELS: Final[frozenset[RiskLevel]] = frozenset({RiskLevel.HIGH, RiskLevel.CRITICAL})
"""The bands that require CAB review rather than a simple approval --
see ``app/changes/engine.py::requires_cab_review``."""


def priority_at_least(candidate: ChangePriority, floor: ChangePriority) -> bool:
    """Whether *candidate* is at least as urgent as *floor*."""
    return PRIORITY_ORDER[candidate] <= PRIORITY_ORDER[floor]


def risk_at_least(candidate: RiskLevel, floor: RiskLevel) -> bool:
    """Whether *candidate* is at least as severe as *floor*."""
    return RISK_ORDER[candidate] >= RISK_ORDER[floor]


# ---- normalisers ---------------------------------------------------------


def change_type_of(value: str | ChangeType) -> ChangeType:
    """Coerce a stored value to :class:`ChangeType`."""
    return value if isinstance(value, ChangeType) else ChangeType(value)


def change_category_of(value: str | ChangeCategory) -> ChangeCategory:
    """Coerce a stored value to :class:`ChangeCategory`."""
    return value if isinstance(value, ChangeCategory) else ChangeCategory(value)


def change_priority_of(value: str | ChangePriority) -> ChangePriority:
    """Coerce a stored value to :class:`ChangePriority`."""
    return value if isinstance(value, ChangePriority) else ChangePriority(value)


def change_status_of(value: str | ChangeStatus) -> ChangeStatus:
    """Coerce a stored value to :class:`ChangeStatus`."""
    return value if isinstance(value, ChangeStatus) else ChangeStatus(value)


def risk_level_of(value: str | RiskLevel) -> RiskLevel:
    """Coerce a stored value to :class:`RiskLevel`."""
    return value if isinstance(value, RiskLevel) else RiskLevel(value)


def risk_likelihood_of(value: str | RiskLikelihood) -> RiskLikelihood:
    """Coerce a stored value to :class:`RiskLikelihood`."""
    return value if isinstance(value, RiskLikelihood) else RiskLikelihood(value)


def risk_impact_of(value: str | RiskImpact) -> RiskImpact:
    """Coerce a stored value to :class:`RiskImpact`."""
    return value if isinstance(value, RiskImpact) else RiskImpact(value)


def approval_status_of(value: str | ApprovalStatus) -> ApprovalStatus:
    """Coerce a stored value to :class:`ApprovalStatus`."""
    return value if isinstance(value, ApprovalStatus) else ApprovalStatus(value)


def approval_policy_of(value: str | ApprovalPolicy) -> ApprovalPolicy:
    """Coerce a stored value to :class:`ApprovalPolicy`."""
    return value if isinstance(value, ApprovalPolicy) else ApprovalPolicy(value)


def cab_meeting_status_of(value: str | CabMeetingStatus) -> CabMeetingStatus:
    """Coerce a stored value to :class:`CabMeetingStatus`."""
    return value if isinstance(value, CabMeetingStatus) else CabMeetingStatus(value)


def cab_vote_of(value: str | CabVote) -> CabVote:
    """Coerce a stored value to :class:`CabVote`."""
    return value if isinstance(value, CabVote) else CabVote(value)


def calendar_entry_kind_of(value: str | CalendarEntryKind) -> CalendarEntryKind:
    """Coerce a stored value to :class:`CalendarEntryKind`."""
    return value if isinstance(value, CalendarEntryKind) else CalendarEntryKind(value)


def conflict_kind_of(value: str | ConflictKind) -> ConflictKind:
    """Coerce a stored value to :class:`ConflictKind`."""
    return value if isinstance(value, ConflictKind) else ConflictKind(value)


def conflict_status_of(value: str | ConflictStatus) -> ConflictStatus:
    """Coerce a stored value to :class:`ConflictStatus`."""
    return value if isinstance(value, ConflictStatus) else ConflictStatus(value)


def change_task_status_of(value: str | ChangeTaskStatus) -> ChangeTaskStatus:
    """Coerce a stored value to :class:`ChangeTaskStatus`."""
    return value if isinstance(value, ChangeTaskStatus) else ChangeTaskStatus(value)


def implementation_status_of(value: str | ImplementationStatus) -> ImplementationStatus:
    """Coerce a stored value to :class:`ImplementationStatus`."""
    return value if isinstance(value, ImplementationStatus) else ImplementationStatus(value)


def validation_status_of(value: str | ValidationStatus) -> ValidationStatus:
    """Coerce a stored value to :class:`ValidationStatus`."""
    return value if isinstance(value, ValidationStatus) else ValidationStatus(value)


def rollback_status_of(value: str | RollbackStatus) -> RollbackStatus:
    """Coerce a stored value to :class:`RollbackStatus`."""
    return value if isinstance(value, RollbackStatus) else RollbackStatus(value)


def pir_status_of(value: str | PirStatus) -> PirStatus:
    """Coerce a stored value to :class:`PirStatus`."""
    return value if isinstance(value, PirStatus) else PirStatus(value)


def report_kind_of(value: str | ReportKind) -> ReportKind:
    """Coerce a stored value to :class:`ReportKind`."""
    return value if isinstance(value, ReportKind) else ReportKind(value)


def report_format_of(value: str | ReportFormat) -> ReportFormat:
    """Coerce a stored value to :class:`ReportFormat`."""
    return value if isinstance(value, ReportFormat) else ReportFormat(value)


def job_status_of(value: str | JobStatus) -> JobStatus:
    """Coerce a stored value to :class:`JobStatus`."""
    return value if isinstance(value, JobStatus) else JobStatus(value)


__all__ = [
    "HIGH_RISK_LEVELS",
    "IMPACT_ORDER",
    "LIKELIHOOD_ORDER",
    "OPEN_CHANGE_STATUSES",
    "PRIORITY_ORDER",
    "RISK_ORDER",
    "TERMINAL_CHANGE_STATUSES",
    "ApprovalPolicy",
    "ApprovalStatus",
    "AuditAction",
    "CabMeetingStatus",
    "CabVote",
    "CalendarEntryKind",
    "ChangeCategory",
    "ChangePriority",
    "ChangeStatus",
    "ChangeTaskStatus",
    "ChangeType",
    "ConflictKind",
    "ConflictStatus",
    "ImplementationStatus",
    "JobStatus",
    "PirStatus",
    "RecurrenceKind",
    "RelationshipKind",
    "ReportFormat",
    "ReportKind",
    "RiskImpact",
    "RiskLevel",
    "RiskLikelihood",
    "RollbackStatus",
    "ValidationKind",
    "ValidationStatus",
    "approval_policy_of",
    "approval_status_of",
    "cab_meeting_status_of",
    "cab_vote_of",
    "calendar_entry_kind_of",
    "change_category_of",
    "change_priority_of",
    "change_status_of",
    "change_task_status_of",
    "change_type_of",
    "conflict_kind_of",
    "conflict_status_of",
    "implementation_status_of",
    "job_status_of",
    "pir_status_of",
    "priority_at_least",
    "report_format_of",
    "report_kind_of",
    "risk_at_least",
    "risk_impact_of",
    "risk_level_of",
    "risk_likelihood_of",
    "rollback_status_of",
    "validation_status_of",
]
