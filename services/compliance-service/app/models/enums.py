"""The compliance vocabulary (docs/051).

Every enum here is stored as a string, so a value that reaches the
database outlives the code that wrote it. That is deliberate for an
audit-bearing service -- a finding raised in 2026 must still read
correctly in 2031 -- and it is why each one carries an ``X_of()``
normaliser: a ``Mapped[SomeEnum]`` column backed by ``String`` returns a
plain ``str`` when SQLAlchemy loads it from Postgres, not the enum
member you annotated.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Final


class FrameworkKind(StrEnum):
    """What sort of standard a framework represents.

    The distinction matters for reporting: an auditor asking "are we
    SOC 2 compliant?" wants regulatory frameworks only, and an
    organization's own rules answering in the same list would overstate
    the external position.
    """

    REGULATORY = "regulatory"
    SECURITY = "security"
    INDUSTRIAL = "industrial"
    ORGANIZATIONAL = "organizational"
    CUSTOM = "custom"


class FrameworkCode(StrEnum):
    """The standards this service ships knowledge of.

    A closed enum rather than free text, because control mappings are
    keyed on it and a typo would silently create a second, empty
    framework that reports 100% compliant.
    """

    CIS_BENCHMARKS = "cis_benchmarks"
    NIST_CSF = "nist_csf"
    NIST_800_53 = "nist_800_53"
    ISO_27001 = "iso_27001"
    PCI_DSS = "pci_dss"
    SOC_2 = "soc_2"
    IEC_62443 = "iec_62443"
    IEC_61511 = "iec_61511"
    O_PAS = "o_pas"
    OPEN_PROCESS_AUTOMATION = "open_process_automation"
    ORGANIZATION_POLICY = "organization_policy"
    CUSTOM = "custom"


class FrameworkStatus(StrEnum):
    """Whether a framework counts toward scores."""

    DRAFT = "draft"
    ACTIVE = "active"
    DEPRECATED = "deprecated"
    ARCHIVED = "archived"


class ControlCategory(StrEnum):
    """What area of the estate a control governs."""

    ACCESS_CONTROL = "access_control"
    ASSET_MANAGEMENT = "asset_management"
    CONFIGURATION = "configuration"
    CRYPTOGRAPHY = "cryptography"
    DATA_PROTECTION = "data_protection"
    INCIDENT_RESPONSE = "incident_response"
    LOGGING_MONITORING = "logging_monitoring"
    NETWORK_SECURITY = "network_security"
    PHYSICAL_SECURITY = "physical_security"
    RESILIENCE = "resilience"
    RISK_MANAGEMENT = "risk_management"
    SUPPLY_CHAIN = "supply_chain"
    VULNERABILITY_MANAGEMENT = "vulnerability_management"
    GOVERNANCE = "governance"
    SAFETY = "safety"
    OTHER = "other"


class ControlStatus(StrEnum):
    """Where a control stands in an organization's programme.

    ``NOT_APPLICABLE`` is separate from ``NOT_IMPLEMENTED`` and the
    difference is the whole point: an unimplemented control is a gap
    that lowers the score, a non-applicable one is excluded from the
    denominator entirely. Conflating them either invents failures or
    hides them.
    """

    NOT_IMPLEMENTED = "not_implemented"
    PLANNED = "planned"
    PARTIALLY_IMPLEMENTED = "partially_implemented"
    IMPLEMENTED = "implemented"
    NOT_APPLICABLE = "not_applicable"
    INHERITED = "inherited"


class ControlSeverity(StrEnum):
    """How much a control's failure matters.

    Drives the weight a control carries in its framework's score, via
    :data:`SEVERITY_WEIGHTS`.
    """

    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    INFORMATIONAL = "informational"


class ControlRelationKind(StrEnum):
    """How two controls relate across or within frameworks.

    ``EQUIVALENT_TO`` is what makes one assessment answer several
    frameworks at once -- ISO 27001 A.9.2.3 and NIST 800-53 AC-6 ask the
    same question, and evaluating the estate twice to answer it would be
    both wasteful and a source of contradictory results.
    """

    EQUIVALENT_TO = "equivalent_to"
    DERIVED_FROM = "derived_from"
    SUPPORTS = "supports"
    SUPERSEDES = "supersedes"
    RELATED_TO = "related_to"


class AssessmentKind(StrEnum):
    """What triggered an assessment."""

    CONTINUOUS = "continuous"
    SCHEDULED = "scheduled"
    MANUAL = "manual"
    ON_DEMAND = "on_demand"


class AssessmentScope(StrEnum):
    """What an assessment covers."""

    ORGANIZATION = "organization"
    PROJECT = "project"
    ASSET = "asset"
    FRAMEWORK = "framework"
    CONTROL = "control"


class AssessmentStatus(StrEnum):
    """An assessment run's lifecycle."""

    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    PARTIAL = "partial"


class ScanKind(StrEnum):
    """Which surface a scan interrogates."""

    CONFIGURATION = "configuration"
    INFRASTRUCTURE = "infrastructure"
    SECURITY = "security"
    COMPLIANCE = "compliance"
    CLOUD = "cloud"
    KUBERNETES = "kubernetes"
    INDUSTRIAL = "industrial"
    APPLICATION = "application"
    NETWORK = "network"
    CUSTOM = "custom"


class ScanStatus(StrEnum):
    """A scan's lifecycle."""

    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class ResultStatus(StrEnum):
    """The verdict on one control, for one target.

    ``ERROR`` and ``NOT_ASSESSED`` are both distinct from ``FAIL``, and
    keeping them apart is what stops a broken collector from being
    reported as a compliance failure -- or, worse, a broken collector
    that reports ``PASS`` by default.
    """

    PASS = "pass"
    FAIL = "fail"
    WARNING = "warning"
    NOT_APPLICABLE = "not_applicable"
    NOT_ASSESSED = "not_assessed"
    ERROR = "error"
    EXCEPTED = "excepted"


class FindingSeverity(StrEnum):
    """How badly a finding needs attention."""

    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    INFORMATIONAL = "informational"


class FindingStatus(StrEnum):
    """A finding's lifecycle.

    ``RISK_ACCEPTED`` is not ``RESOLVED``: the condition is still there,
    somebody decided to live with it, and an audit needs to see which of
    the two happened.
    """

    OPEN = "open"
    ACKNOWLEDGED = "acknowledged"
    IN_PROGRESS = "in_progress"
    REMEDIATED = "remediated"
    VERIFIED = "verified"
    RISK_ACCEPTED = "risk_accepted"
    FALSE_POSITIVE = "false_positive"
    CLOSED = "closed"


class EvidenceKind(StrEnum):
    """What sort of proof an evidence record holds."""

    CONFIGURATION_SNAPSHOT = "configuration_snapshot"
    VALIDATION_RESULT = "validation_result"
    AUTOMATION_RESULT = "automation_result"
    MONITORING_METRIC = "monitoring_metric"
    SYSTEM_LOG = "system_log"
    AUDIT_LOG = "audit_log"
    REPORT = "report"
    SCREENSHOT = "screenshot"
    UPLOADED_DOCUMENT = "uploaded_document"
    API_RESPONSE = "api_response"
    CUSTOM = "custom"


class EvidenceSource(StrEnum):
    """Which platform service produced a piece of evidence.

    Named services rather than free text because "where did this proof
    come from?" is the first question an auditor asks, and the answer
    has to be checkable.
    """

    INVENTORY = "inventory"
    DISCOVERY = "discovery"
    CONFIGURATION_MANAGEMENT = "configuration_management"
    AUTOMATION = "automation"
    WORKFLOW_RUNTIME = "workflow_runtime"
    VALIDATION = "validation"
    MONITORING = "monitoring"
    ALERTING = "alerting"
    AI_ASSISTANT = "ai_assistant"
    POLICY_ENGINE = "policy_engine"
    MANUAL_UPLOAD = "manual_upload"
    EXTERNAL = "external"


class ExceptionKind(StrEnum):
    """Whether a waiver ends.

    ``PERMANENT`` exists because docs/051 names it, and it still carries
    a mandatory review cycle: a waiver nobody ever looks at again is an
    undocumented policy change, whatever it is called.
    """

    TEMPORARY = "temporary"
    PERMANENT = "permanent"
    RISK_ACCEPTANCE = "risk_acceptance"
    COMPENSATING_CONTROL = "compensating_control"


class ExceptionStatus(StrEnum):
    """A waiver's lifecycle."""

    REQUESTED = "requested"
    APPROVED = "approved"
    REJECTED = "rejected"
    ACTIVE = "active"
    EXPIRED = "expired"
    REVOKED = "revoked"
    UNDER_REVIEW = "under_review"


class RiskCategory(StrEnum):
    """What kind of risk an entry represents."""

    OPERATIONAL = "operational"
    SECURITY = "security"
    COMPLIANCE = "compliance"
    FINANCIAL = "financial"
    REPUTATIONAL = "reputational"
    STRATEGIC = "strategic"
    SAFETY = "safety"
    SUPPLY_CHAIN = "supply_chain"
    TECHNOLOGY = "technology"


class RiskLikelihood(StrEnum):
    """How probable a risk is, on the standard five-point scale."""

    RARE = "rare"
    UNLIKELY = "unlikely"
    POSSIBLE = "possible"
    LIKELY = "likely"
    ALMOST_CERTAIN = "almost_certain"


class RiskImpact(StrEnum):
    """How bad a risk would be, on the standard five-point scale."""

    NEGLIGIBLE = "negligible"
    MINOR = "minor"
    MODERATE = "moderate"
    MAJOR = "major"
    SEVERE = "severe"


class RiskSeverity(StrEnum):
    """The product of likelihood and impact, banded.

    Derived rather than entered -- see :func:`severity_for` -- because a
    register where somebody can type "low" next to
    ``almost_certain``/``severe`` is a register that hides exactly the
    risks it exists to surface.
    """

    LOW = "low"
    MODERATE = "moderate"
    HIGH = "high"
    CRITICAL = "critical"


class RiskStatus(StrEnum):
    """Where a risk stands."""

    IDENTIFIED = "identified"
    ASSESSED = "assessed"
    MITIGATING = "mitigating"
    MONITORING = "monitoring"
    ACCEPTED = "accepted"
    TRANSFERRED = "transferred"
    CLOSED = "closed"


class RemediationKind(StrEnum):
    """How a finding is meant to be fixed."""

    AUTOMATED = "automated"
    PLAYBOOK = "playbook"
    WORKFLOW = "workflow"
    CONFIGURATION = "configuration"
    MANUAL = "manual"


class RemediationStatus(StrEnum):
    """A remediation's lifecycle.

    ``VERIFIED`` is separate from ``COMPLETED`` because "we ran the fix"
    and "we confirmed the control now passes" are different claims, and
    only the second one may close a finding.
    """

    PROPOSED = "proposed"
    APPROVED = "approved"
    SCHEDULED = "scheduled"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    VERIFIED = "verified"
    FAILED = "failed"
    CANCELLED = "cancelled"


class ScoreScope(StrEnum):
    """What a stored score is the score *of*."""

    OVERALL = "overall"
    FRAMEWORK = "framework"
    CONTROL = "control"
    ORGANIZATION = "organization"
    PROJECT = "project"
    ASSET = "asset"


class ScoreGrade(StrEnum):
    """A banded reading of a numeric score, for executives."""

    EXCELLENT = "excellent"
    GOOD = "good"
    FAIR = "fair"
    POOR = "poor"
    CRITICAL = "critical"


class ReportKind(StrEnum):
    """Which report a request wants."""

    EXECUTIVE = "executive"
    FRAMEWORK = "framework"
    ASSESSMENT = "assessment"
    EVIDENCE = "evidence"
    RISK = "risk"
    CONTROL = "control"
    EXCEPTION = "exception"
    AUDIT = "audit"
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

    FRAMEWORK_CREATED = "framework_created"
    FRAMEWORK_UPDATED = "framework_updated"
    CONTROL_CREATED = "control_created"
    CONTROL_UPDATED = "control_updated"
    CONTROL_MAPPED = "control_mapped"
    ASSESSMENT_CREATED = "assessment_created"
    ASSESSMENT_COMPLETED = "assessment_completed"
    SCAN_STARTED = "scan_started"
    EVIDENCE_COLLECTED = "evidence_collected"
    FINDING_RAISED = "finding_raised"
    FINDING_UPDATED = "finding_updated"
    EXCEPTION_REQUESTED = "exception_requested"
    EXCEPTION_APPROVED = "exception_approved"
    EXCEPTION_REVOKED = "exception_revoked"
    RISK_REGISTERED = "risk_registered"
    RISK_UPDATED = "risk_updated"
    REMEDIATION_CREATED = "remediation_created"
    REMEDIATION_VERIFIED = "remediation_verified"
    REPORT_GENERATED = "report_generated"
    ADMINISTRATIVE = "administrative"


# ---- weightings and derivations ---------------------------------------

SEVERITY_WEIGHTS: Final[dict[ControlSeverity, float]] = {
    ControlSeverity.CRITICAL: 10.0,
    ControlSeverity.HIGH: 5.0,
    ControlSeverity.MEDIUM: 2.0,
    ControlSeverity.LOW: 1.0,
    ControlSeverity.INFORMATIONAL: 0.0,
}
"""How much each control severity counts toward a framework score.

Informational controls weigh **nothing**. They still produce findings
and still appear in reports, but a hundred passing informational
controls must not be able to drown out one failing critical one -- which
is precisely what an unweighted pass-rate does, and why unweighted
compliance percentages are worth so little.
"""

LIKELIHOOD_VALUES: Final[dict[RiskLikelihood, int]] = {
    RiskLikelihood.RARE: 1,
    RiskLikelihood.UNLIKELY: 2,
    RiskLikelihood.POSSIBLE: 3,
    RiskLikelihood.LIKELY: 4,
    RiskLikelihood.ALMOST_CERTAIN: 5,
}

IMPACT_VALUES: Final[dict[RiskImpact, int]] = {
    RiskImpact.NEGLIGIBLE: 1,
    RiskImpact.MINOR: 2,
    RiskImpact.MODERATE: 3,
    RiskImpact.MAJOR: 4,
    RiskImpact.SEVERE: 5,
}

FINDING_SEVERITY_FOR_CONTROL: Final[dict[ControlSeverity, FindingSeverity]] = {
    ControlSeverity.CRITICAL: FindingSeverity.CRITICAL,
    ControlSeverity.HIGH: FindingSeverity.HIGH,
    ControlSeverity.MEDIUM: FindingSeverity.MEDIUM,
    ControlSeverity.LOW: FindingSeverity.LOW,
    ControlSeverity.INFORMATIONAL: FindingSeverity.INFORMATIONAL,
}

SCORED_STATUSES: Final[frozenset[ResultStatus]] = frozenset(
    {ResultStatus.PASS, ResultStatus.FAIL, ResultStatus.WARNING, ResultStatus.EXCEPTED}
)
"""The verdicts that belong in a score's denominator.

``NOT_APPLICABLE``, ``NOT_ASSESSED``, and ``ERROR`` are excluded, and
the reason differs for each. A non-applicable control was never a
requirement. An unassessed one is unknown, and scoring unknowns as
failures makes a partial run look like a catastrophe while scoring them
as passes makes it look like a success -- both are lies. An errored one
means the collector broke, which is an operational problem, not a
compliance verdict.
"""

FAILING_STATUSES: Final[frozenset[ResultStatus]] = frozenset(
    {ResultStatus.FAIL, ResultStatus.WARNING}
)

OPEN_FINDING_STATUSES: Final[frozenset[FindingStatus]] = frozenset(
    {
        FindingStatus.OPEN,
        FindingStatus.ACKNOWLEDGED,
        FindingStatus.IN_PROGRESS,
    }
)

LIVE_EXCEPTION_STATUSES: Final[frozenset[ExceptionStatus]] = frozenset(
    {ExceptionStatus.APPROVED, ExceptionStatus.ACTIVE}
)

TERMINAL_ASSESSMENT_STATUSES: Final[frozenset[AssessmentStatus]] = frozenset(
    {
        AssessmentStatus.COMPLETED,
        AssessmentStatus.FAILED,
        AssessmentStatus.CANCELLED,
        AssessmentStatus.PARTIAL,
    }
)


def severity_for(likelihood: RiskLikelihood, impact: RiskImpact) -> RiskSeverity:
    """Band a likelihood/impact pair onto the standard 5x5 matrix.

    Derived, never entered. A register that lets somebody type "low"
    beside ``almost_certain``/``severe`` hides exactly the risks it
    exists to surface, and the people most motivated to type it are the
    ones who own the risk.
    """
    score = LIKELIHOOD_VALUES[likelihood] * IMPACT_VALUES[impact]
    if score >= 15:
        return RiskSeverity.CRITICAL
    if score >= 9:
        return RiskSeverity.HIGH
    if score >= 4:
        return RiskSeverity.MODERATE
    return RiskSeverity.LOW


def grade_for(score: float) -> ScoreGrade:
    """Band a 0-100 compliance score for an executive summary."""
    if score >= 95.0:
        return ScoreGrade.EXCELLENT
    if score >= 85.0:
        return ScoreGrade.GOOD
    if score >= 70.0:
        return ScoreGrade.FAIR
    if score >= 50.0:
        return ScoreGrade.POOR
    return ScoreGrade.CRITICAL


# ---- normalisers ------------------------------------------------------
#
# A ``Mapped[SomeEnum]`` column backed by ``String`` hands back a plain
# ``str`` on load, so anything comparing an ORM attribute against an
# enum member silently fails. Every enum stored on a model gets one of
# these, and callers use it rather than trusting the annotation.


def framework_kind_of(value: str | FrameworkKind) -> FrameworkKind:
    """Coerce a stored value to :class:`FrameworkKind`."""
    return value if isinstance(value, FrameworkKind) else FrameworkKind(value)


def framework_code_of(value: str | FrameworkCode) -> FrameworkCode:
    """Coerce a stored value to :class:`FrameworkCode`."""
    return value if isinstance(value, FrameworkCode) else FrameworkCode(value)


def framework_status_of(value: str | FrameworkStatus) -> FrameworkStatus:
    """Coerce a stored value to :class:`FrameworkStatus`."""
    return value if isinstance(value, FrameworkStatus) else FrameworkStatus(value)


def control_status_of(value: str | ControlStatus) -> ControlStatus:
    """Coerce a stored value to :class:`ControlStatus`."""
    return value if isinstance(value, ControlStatus) else ControlStatus(value)


def control_severity_of(value: str | ControlSeverity) -> ControlSeverity:
    """Coerce a stored value to :class:`ControlSeverity`."""
    return value if isinstance(value, ControlSeverity) else ControlSeverity(value)


def control_category_of(value: str | ControlCategory) -> ControlCategory:
    """Coerce a stored value to :class:`ControlCategory`."""
    return value if isinstance(value, ControlCategory) else ControlCategory(value)


def assessment_status_of(value: str | AssessmentStatus) -> AssessmentStatus:
    """Coerce a stored value to :class:`AssessmentStatus`."""
    return value if isinstance(value, AssessmentStatus) else AssessmentStatus(value)


def assessment_scope_of(value: str | AssessmentScope) -> AssessmentScope:
    """Coerce a stored value to :class:`AssessmentScope`."""
    return value if isinstance(value, AssessmentScope) else AssessmentScope(value)


def scan_status_of(value: str | ScanStatus) -> ScanStatus:
    """Coerce a stored value to :class:`ScanStatus`."""
    return value if isinstance(value, ScanStatus) else ScanStatus(value)


def result_status_of(value: str | ResultStatus) -> ResultStatus:
    """Coerce a stored value to :class:`ResultStatus`."""
    return value if isinstance(value, ResultStatus) else ResultStatus(value)


def finding_status_of(value: str | FindingStatus) -> FindingStatus:
    """Coerce a stored value to :class:`FindingStatus`."""
    return value if isinstance(value, FindingStatus) else FindingStatus(value)


def finding_severity_of(value: str | FindingSeverity) -> FindingSeverity:
    """Coerce a stored value to :class:`FindingSeverity`."""
    return value if isinstance(value, FindingSeverity) else FindingSeverity(value)


def evidence_kind_of(value: str | EvidenceKind) -> EvidenceKind:
    """Coerce a stored value to :class:`EvidenceKind`."""
    return value if isinstance(value, EvidenceKind) else EvidenceKind(value)


def exception_status_of(value: str | ExceptionStatus) -> ExceptionStatus:
    """Coerce a stored value to :class:`ExceptionStatus`."""
    return value if isinstance(value, ExceptionStatus) else ExceptionStatus(value)


def exception_kind_of(value: str | ExceptionKind) -> ExceptionKind:
    """Coerce a stored value to :class:`ExceptionKind`."""
    return value if isinstance(value, ExceptionKind) else ExceptionKind(value)


def risk_likelihood_of(value: str | RiskLikelihood) -> RiskLikelihood:
    """Coerce a stored value to :class:`RiskLikelihood`."""
    return value if isinstance(value, RiskLikelihood) else RiskLikelihood(value)


def risk_impact_of(value: str | RiskImpact) -> RiskImpact:
    """Coerce a stored value to :class:`RiskImpact`."""
    return value if isinstance(value, RiskImpact) else RiskImpact(value)


def risk_severity_of(value: str | RiskSeverity) -> RiskSeverity:
    """Coerce a stored value to :class:`RiskSeverity`."""
    return value if isinstance(value, RiskSeverity) else RiskSeverity(value)


def risk_status_of(value: str | RiskStatus) -> RiskStatus:
    """Coerce a stored value to :class:`RiskStatus`."""
    return value if isinstance(value, RiskStatus) else RiskStatus(value)


def remediation_status_of(value: str | RemediationStatus) -> RemediationStatus:
    """Coerce a stored value to :class:`RemediationStatus`."""
    return value if isinstance(value, RemediationStatus) else RemediationStatus(value)


def report_kind_of(value: str | ReportKind) -> ReportKind:
    """Coerce a stored value to :class:`ReportKind`."""
    return value if isinstance(value, ReportKind) else ReportKind(value)


def report_format_of(value: str | ReportFormat) -> ReportFormat:
    """Coerce a stored value to :class:`ReportFormat`."""
    return value if isinstance(value, ReportFormat) else ReportFormat(value)


__all__ = [
    "FAILING_STATUSES",
    "FINDING_SEVERITY_FOR_CONTROL",
    "IMPACT_VALUES",
    "LIKELIHOOD_VALUES",
    "LIVE_EXCEPTION_STATUSES",
    "OPEN_FINDING_STATUSES",
    "SCORED_STATUSES",
    "SEVERITY_WEIGHTS",
    "TERMINAL_ASSESSMENT_STATUSES",
    "AssessmentKind",
    "AssessmentScope",
    "AssessmentStatus",
    "AuditAction",
    "ControlCategory",
    "ControlRelationKind",
    "ControlSeverity",
    "ControlStatus",
    "EvidenceKind",
    "EvidenceSource",
    "ExceptionKind",
    "ExceptionStatus",
    "FindingSeverity",
    "FindingStatus",
    "FrameworkCode",
    "FrameworkKind",
    "FrameworkStatus",
    "JobStatus",
    "RemediationKind",
    "RemediationStatus",
    "ReportFormat",
    "ReportKind",
    "ResultStatus",
    "RiskCategory",
    "RiskImpact",
    "RiskLikelihood",
    "RiskSeverity",
    "RiskStatus",
    "ScanKind",
    "ScanStatus",
    "ScoreGrade",
    "ScoreScope",
    "assessment_scope_of",
    "assessment_status_of",
    "control_category_of",
    "control_severity_of",
    "control_status_of",
    "evidence_kind_of",
    "exception_kind_of",
    "exception_status_of",
    "finding_severity_of",
    "finding_status_of",
    "framework_code_of",
    "framework_kind_of",
    "framework_status_of",
    "grade_for",
    "remediation_status_of",
    "report_format_of",
    "report_kind_of",
    "result_status_of",
    "risk_impact_of",
    "risk_likelihood_of",
    "risk_severity_of",
    "risk_status_of",
    "scan_status_of",
    "severity_for",
]
