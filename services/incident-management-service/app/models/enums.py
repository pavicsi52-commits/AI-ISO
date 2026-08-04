"""The incident management vocabulary (docs/052).

Every enum here is stored as a string, so a value written today outlives
the code that wrote it — an incident closed in 2026 must still read
correctly during a 2031 audit of that quarter's MTTR. Each therefore
carries an ``X_of()`` normaliser: a ``Mapped[SomeEnum]`` column backed by
``String`` returns a plain ``str`` on load, not the enum member you
annotated.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Final


class IncidentSource(StrEnum):
    """Where an incident came from.

    Kept distinct from *category* on purpose: an incident's source is
    how the platform learned about it, its category is what kind of
    problem it is. A monitoring-sourced incident can be a database
    category one, and conflating the two would make "how many incidents
    did monitoring actually catch versus a human report" unanswerable.
    """

    MONITORING = "monitoring"
    ALERTING = "alerting"
    VALIDATION = "validation"
    AUTOMATION = "automation"
    WORKFLOW_RUNTIME = "workflow_runtime"
    CONFIGURATION_MANAGEMENT = "configuration_management"
    KNOWLEDGE_GRAPH = "knowledge_graph"
    MANUAL = "manual"
    REST_API = "rest_api"
    WEBHOOK = "webhook"
    EMAIL = "email"
    CUSTOM = "custom"


class IncidentCategory(StrEnum):
    """What area of the estate an incident affects."""

    INFRASTRUCTURE = "infrastructure"
    APPLICATION = "application"
    DATABASE = "database"
    NETWORK = "network"
    STORAGE = "storage"
    CLOUD = "cloud"
    KUBERNETES = "kubernetes"
    CONTAINER = "container"
    SECURITY = "security"
    COMPLIANCE = "compliance"
    AUTOMATION = "automation"
    WORKFLOW = "workflow"
    CONFIGURATION = "configuration"
    INDUSTRIAL = "industrial"
    EDGE = "edge"
    SERVICE_AVAILABILITY = "service_availability"
    PERFORMANCE = "performance"
    CAPACITY = "capacity"
    BACKUP = "backup"
    DISASTER_RECOVERY = "disaster_recovery"
    CUSTOM = "custom"


class IncidentPriority(StrEnum):
    """The standard five-level incident priority scale."""

    P1_CRITICAL = "p1_critical"
    P2_HIGH = "p2_high"
    P3_MEDIUM = "p3_medium"
    P4_LOW = "p4_low"
    P5_INFORMATIONAL = "p5_informational"


class IncidentStatus(StrEnum):
    """Where an incident stands in its lifecycle.

    ``MERGED`` is not ``CLOSED``: a merged incident's history and
    worklog survive under the incident it merged into, and reporting
    that counted it as independently closed would double-count one
    outage as two.
    """

    NEW = "new"
    ASSIGNED = "assigned"
    ACKNOWLEDGED = "acknowledged"
    INVESTIGATING = "investigating"
    MITIGATING = "mitigating"
    MONITORING = "monitoring"
    RESOLVED = "resolved"
    CLOSED = "closed"
    CANCELLED = "cancelled"
    MERGED = "merged"


class ImpactLevel(StrEnum):
    """How severely one affected thing is impacted."""

    NONE = "none"
    MINOR = "minor"
    MODERATE = "moderate"
    MAJOR = "major"
    SEVERE = "severe"


class RiskLevel(StrEnum):
    """A coarse risk banding for an incident's blast radius."""

    LOW = "low"
    MODERATE = "moderate"
    HIGH = "high"
    CRITICAL = "critical"


class AssignmentMethod(StrEnum):
    """How an incident came to have its current assignee."""

    MANUAL = "manual"
    AUTOMATIC = "automatic"
    LOAD_BALANCED = "load_balanced"
    SKILL_BASED = "skill_based"
    ON_CALL = "on_call"
    ESCALATION = "escalation"


class EscalationTrigger(StrEnum):
    """What caused an escalation to fire."""

    TIME_BASED = "time_based"
    ROLE = "role"
    MANAGER = "manager"
    EXECUTIVE = "executive"
    WORKFLOW = "workflow"
    AUTOMATION = "automation"
    POLICY = "policy"
    MANUAL = "manual"


class EscalationStatus(StrEnum):
    """An escalation's own lifecycle."""

    PENDING = "pending"
    TRIGGERED = "triggered"
    ACKNOWLEDGED = "acknowledged"
    CANCELLED = "cancelled"


class SlaKind(StrEnum):
    """Which clock an SLA measures."""

    RESPONSE = "response"
    ACKNOWLEDGEMENT = "acknowledgement"
    RESOLUTION = "resolution"
    ESCALATION = "escalation"


class SlaStatus(StrEnum):
    """Where one SLA clock stands.

    ``PAUSED`` is distinct from simply not running: a paused clock has
    accumulated time that must be excluded when resumed, which is
    exactly what :func:`~app.sla.engine.elapsed_seconds` accounts for.
    """

    PENDING = "pending"
    RUNNING = "running"
    PAUSED = "paused"
    MET = "met"
    BREACHED = "breached"
    CANCELLED = "cancelled"


class WarRoomStatus(StrEnum):
    """A war room's lifecycle."""

    OPEN = "open"
    ACTIVE = "active"
    STANDING_DOWN = "standing_down"
    CLOSED = "closed"


class WarRoomRole(StrEnum):
    """A war room participant's function.

    Named roles rather than free text because exactly one person may
    hold ``INCIDENT_COMMANDER`` at a time — see
    :data:`SINGLETON_WAR_ROOM_ROLES` — and enforcing that requires the
    role to be a closed set the service can reason about.
    """

    INCIDENT_COMMANDER = "incident_commander"
    COMMUNICATION_LEAD = "communication_lead"
    TECHNICAL_LEAD = "technical_lead"
    BUSINESS_LEAD = "business_lead"
    PARTICIPANT = "participant"
    OBSERVER = "observer"


class RcaMethod(StrEnum):
    """How a root cause was determined."""

    MANUAL = "manual"
    DEPENDENCY_ANALYSIS = "dependency_analysis"
    KNOWLEDGE_GRAPH_TRAVERSAL = "knowledge_graph_traversal"
    ALERT_CORRELATION = "alert_correlation"
    VALIDATION_RESULTS = "validation_results"
    AUTOMATION_HISTORY = "automation_history"
    CONFIGURATION_DRIFT = "configuration_drift"
    AI_ASSISTED = "ai_assisted"
    FIVE_WHYS = "five_whys"
    FISHBONE = "fishbone"
    TIMELINE_CORRELATION = "timeline_correlation"


class TimelineEventKind(StrEnum):
    """What sort of thing a timeline entry records.

    ``SYSTEM`` entries (status changes, assignment, SLA events) are
    generated by this service; ``NOTE`` and ``COMMUNICATION`` are
    authored by a person. Kept distinct so a timeline can be filtered to
    "what actually happened" without the narration a person added
    around it.
    """

    CREATED = "created"
    STATUS_CHANGE = "status_change"
    ASSIGNMENT = "assignment"
    ESCALATION = "escalation"
    NOTE = "note"
    COMMUNICATION = "communication"
    AUTOMATION_ACTION = "automation_action"
    WORKFLOW_ACTION = "workflow_action"
    SLA_EVENT = "sla_event"
    IMPACT_UPDATE = "impact_update"
    ROOT_CAUSE_UPDATE = "root_cause_update"
    MERGE = "merge"
    SYSTEM = "system"


class PostmortemStatus(StrEnum):
    """A postmortem document's lifecycle."""

    DRAFT = "draft"
    IN_REVIEW = "in_review"
    APPROVED = "approved"
    PUBLISHED = "published"


class ActionItemStatus(StrEnum):
    """A postmortem action item's lifecycle."""

    OPEN = "open"
    IN_PROGRESS = "in_progress"
    DONE = "done"
    CANCELLED = "cancelled"


class ProblemStatus(StrEnum):
    """A problem record's lifecycle.

    ``KNOWN_ERROR`` is a distinct status, not a separate table's-worth
    of state: a problem becomes a known error the moment its root cause
    is understood, whether or not a permanent fix exists yet.
    """

    OPEN = "open"
    INVESTIGATING = "investigating"
    KNOWN_ERROR = "known_error"
    RESOLVED = "resolved"
    CLOSED = "closed"


class WorklogKind(StrEnum):
    """What sort of work a worklog entry records."""

    INVESTIGATION = "investigation"
    MITIGATION = "mitigation"
    COMMUNICATION = "communication"
    ESCALATION = "escalation"
    VERIFICATION = "verification"
    OTHER = "other"


class ReportKind(StrEnum):
    """Which report a request wants."""

    INCIDENT = "incident"
    EXECUTIVE = "executive"
    MAJOR_INCIDENT = "major_incident"
    SLA = "sla"
    ROOT_CAUSE = "root_cause"
    PROBLEM = "problem"
    POSTMORTEM = "postmortem"
    TREND = "trend"


class ReportFormat(StrEnum):
    """How a report is rendered."""

    JSON = "json"
    CSV = "csv"
    MARKDOWN = "markdown"


class JobStatus(StrEnum):
    """A background job's lifecycle."""

    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class AuditAction(StrEnum):
    """What an audit row records."""

    INCIDENT_CREATED = "incident_created"
    INCIDENT_UPDATED = "incident_updated"
    STATUS_CHANGED = "status_changed"
    ASSIGNED = "assigned"
    ESCALATED = "escalated"
    MAJOR_INCIDENT_DECLARED = "major_incident_declared"
    WAR_ROOM_OPENED = "war_room_opened"
    WAR_ROOM_CLOSED = "war_room_closed"
    ROOT_CAUSE_RECORDED = "root_cause_recorded"
    POSTMORTEM_CREATED = "postmortem_created"
    POSTMORTEM_APPROVED = "postmortem_approved"
    PROBLEM_CREATED = "problem_created"
    KNOWN_ERROR_RECORDED = "known_error_recorded"
    REPORT_GENERATED = "report_generated"
    ADMINISTRATIVE = "administrative"


# ---- weightings and derivations ----------------------------------------

PRIORITY_ORDER: Final[dict[IncidentPriority, int]] = {
    IncidentPriority.P1_CRITICAL: 0,
    IncidentPriority.P2_HIGH: 1,
    IncidentPriority.P3_MEDIUM: 2,
    IncidentPriority.P4_LOW: 3,
    IncidentPriority.P5_INFORMATIONAL: 4,
}
"""Lower sorts first. P1 is 0 rather than 1 so it can be used directly as
a sort key without an off-by-one, and so that "more urgent" is always
"numerically smaller" throughout the codebase -- one convention, not two."""

IMPACT_ORDER: Final[dict[ImpactLevel, int]] = {
    ImpactLevel.NONE: 0,
    ImpactLevel.MINOR: 1,
    ImpactLevel.MODERATE: 2,
    ImpactLevel.MAJOR: 3,
    ImpactLevel.SEVERE: 4,
}

OPEN_INCIDENT_STATUSES: Final[frozenset[IncidentStatus]] = frozenset(
    {
        IncidentStatus.NEW,
        IncidentStatus.ASSIGNED,
        IncidentStatus.ACKNOWLEDGED,
        IncidentStatus.INVESTIGATING,
        IncidentStatus.MITIGATING,
        IncidentStatus.MONITORING,
    }
)
"""Statuses that count as "still open" for MTTR, load-balancing, and
dashboards. ``RESOLVED`` is deliberately excluded -- a resolved incident
is not open work, even though it has not been formally closed yet."""

TERMINAL_INCIDENT_STATUSES: Final[frozenset[IncidentStatus]] = frozenset(
    {IncidentStatus.CLOSED, IncidentStatus.CANCELLED, IncidentStatus.MERGED}
)

SINGLETON_WAR_ROOM_ROLES: Final[frozenset[WarRoomRole]] = frozenset(
    {
        WarRoomRole.INCIDENT_COMMANDER,
        WarRoomRole.COMMUNICATION_LEAD,
        WarRoomRole.TECHNICAL_LEAD,
        WarRoomRole.BUSINESS_LEAD,
    }
)
"""Roles exactly one participant may hold at a time.

Two incident commanders is not redundancy, it is two people who each
believe they have final say -- the exact failure mode a named-commander
model exists to prevent. ``PARTICIPANT`` and ``OBSERVER`` are
deliberately absent: many people legitimately hold those at once."""

DEFAULT_SLA_MINUTES: Final[dict[IncidentPriority, dict[SlaKind, int]]] = {
    IncidentPriority.P1_CRITICAL: {
        SlaKind.RESPONSE: 5,
        SlaKind.ACKNOWLEDGEMENT: 15,
        SlaKind.RESOLUTION: 240,
    },
    IncidentPriority.P2_HIGH: {
        SlaKind.RESPONSE: 15,
        SlaKind.ACKNOWLEDGEMENT: 30,
        SlaKind.RESOLUTION: 480,
    },
    IncidentPriority.P3_MEDIUM: {
        SlaKind.RESPONSE: 60,
        SlaKind.ACKNOWLEDGEMENT: 120,
        SlaKind.RESOLUTION: 1_440,
    },
    IncidentPriority.P4_LOW: {
        SlaKind.RESPONSE: 240,
        SlaKind.ACKNOWLEDGEMENT: 480,
        SlaKind.RESOLUTION: 4_320,
    },
    IncidentPriority.P5_INFORMATIONAL: {
        SlaKind.RESPONSE: 1_440,
        SlaKind.ACKNOWLEDGEMENT: 2_880,
        SlaKind.RESOLUTION: 10_080,
    },
}
"""Organization-configurable defaults, in minutes, seeded onto a new
incident's SLA clocks. Deliberately absent for ``SlaKind.ESCALATION`` --
an escalation SLA only exists where an organization has actually
configured an escalation policy, and inventing a default here would
start a clock nobody agreed to and could not explain being breached."""


def priority_at_least(priority: IncidentPriority, floor: IncidentPriority) -> bool:
    """Whether *priority* is at least as urgent as *floor*.

    Reads naturally at call sites -- ``priority_at_least(p, P2_HIGH)`` --
    which a bare comparison on :data:`PRIORITY_ORDER` (lower-is-more-
    urgent) would not: ``PRIORITY_ORDER[p] <= PRIORITY_ORDER[floor]``
    inverts the intuitive direction and is exactly the kind of line that
    gets the comparison operator backwards during a later edit.
    """
    return PRIORITY_ORDER[priority] <= PRIORITY_ORDER[floor]


# ---- normalisers ---------------------------------------------------------
#
# A ``Mapped[SomeEnum]`` column backed by ``String`` hands back a plain
# ``str`` on load, so anything comparing an ORM attribute against an enum
# member silently fails. Every enum stored on a model gets one of these,
# and callers use it rather than trusting the annotation.


def incident_status_of(value: str | IncidentStatus) -> IncidentStatus:
    """Coerce a stored value to :class:`IncidentStatus`."""
    return value if isinstance(value, IncidentStatus) else IncidentStatus(value)


def incident_priority_of(value: str | IncidentPriority) -> IncidentPriority:
    """Coerce a stored value to :class:`IncidentPriority`."""
    return value if isinstance(value, IncidentPriority) else IncidentPriority(value)


def incident_category_of(value: str | IncidentCategory) -> IncidentCategory:
    """Coerce a stored value to :class:`IncidentCategory`."""
    return value if isinstance(value, IncidentCategory) else IncidentCategory(value)


def impact_level_of(value: str | ImpactLevel) -> ImpactLevel:
    """Coerce a stored value to :class:`ImpactLevel`."""
    return value if isinstance(value, ImpactLevel) else ImpactLevel(value)


def sla_status_of(value: str | SlaStatus) -> SlaStatus:
    """Coerce a stored value to :class:`SlaStatus`."""
    return value if isinstance(value, SlaStatus) else SlaStatus(value)


def sla_kind_of(value: str | SlaKind) -> SlaKind:
    """Coerce a stored value to :class:`SlaKind`."""
    return value if isinstance(value, SlaKind) else SlaKind(value)


def war_room_status_of(value: str | WarRoomStatus) -> WarRoomStatus:
    """Coerce a stored value to :class:`WarRoomStatus`."""
    return value if isinstance(value, WarRoomStatus) else WarRoomStatus(value)


def war_room_role_of(value: str | WarRoomRole) -> WarRoomRole:
    """Coerce a stored value to :class:`WarRoomRole`."""
    return value if isinstance(value, WarRoomRole) else WarRoomRole(value)


def escalation_status_of(value: str | EscalationStatus) -> EscalationStatus:
    """Coerce a stored value to :class:`EscalationStatus`."""
    return value if isinstance(value, EscalationStatus) else EscalationStatus(value)


def postmortem_status_of(value: str | PostmortemStatus) -> PostmortemStatus:
    """Coerce a stored value to :class:`PostmortemStatus`."""
    return value if isinstance(value, PostmortemStatus) else PostmortemStatus(value)


def action_item_status_of(value: str | ActionItemStatus) -> ActionItemStatus:
    """Coerce a stored value to :class:`ActionItemStatus`."""
    return value if isinstance(value, ActionItemStatus) else ActionItemStatus(value)


def problem_status_of(value: str | ProblemStatus) -> ProblemStatus:
    """Coerce a stored value to :class:`ProblemStatus`."""
    return value if isinstance(value, ProblemStatus) else ProblemStatus(value)


def report_kind_of(value: str | ReportKind) -> ReportKind:
    """Coerce a stored value to :class:`ReportKind`."""
    return value if isinstance(value, ReportKind) else ReportKind(value)


def report_format_of(value: str | ReportFormat) -> ReportFormat:
    """Coerce a stored value to :class:`ReportFormat`."""
    return value if isinstance(value, ReportFormat) else ReportFormat(value)


__all__ = [
    "DEFAULT_SLA_MINUTES",
    "IMPACT_ORDER",
    "OPEN_INCIDENT_STATUSES",
    "PRIORITY_ORDER",
    "SINGLETON_WAR_ROOM_ROLES",
    "TERMINAL_INCIDENT_STATUSES",
    "ActionItemStatus",
    "AssignmentMethod",
    "AuditAction",
    "EscalationStatus",
    "EscalationTrigger",
    "ImpactLevel",
    "IncidentCategory",
    "IncidentPriority",
    "IncidentSource",
    "IncidentStatus",
    "JobStatus",
    "PostmortemStatus",
    "ProblemStatus",
    "RcaMethod",
    "ReportFormat",
    "ReportKind",
    "RiskLevel",
    "SlaKind",
    "SlaStatus",
    "TimelineEventKind",
    "WarRoomRole",
    "WarRoomStatus",
    "WorklogKind",
    "action_item_status_of",
    "escalation_status_of",
    "impact_level_of",
    "incident_category_of",
    "incident_priority_of",
    "incident_status_of",
    "postmortem_status_of",
    "priority_at_least",
    "problem_status_of",
    "report_format_of",
    "report_kind_of",
    "sla_kind_of",
    "sla_status_of",
    "war_room_role_of",
    "war_room_status_of",
]
