"""Enumerations for the validation service.

Every enum member is verbatim from docs/043's own named lists except
where noted -- each such deviation is explained inline rather than
silently invented.
"""

from __future__ import annotations

from enum import StrEnum


class ValidationType(StrEnum):
    """Per docs/043's own "VALIDATION TYPES" list (20 values, verbatim)."""

    INFRASTRUCTURE = "infrastructure"
    ENVIRONMENT = "environment"
    CONFIGURATION = "configuration"
    DEPLOYMENT = "deployment"
    POST_DEPLOYMENT = "post_deployment"
    HEALTH = "health"
    CONNECTIVITY = "connectivity"
    SECURITY = "security"
    COMPLIANCE = "compliance"
    PATCH = "patch"
    FIRMWARE = "firmware"
    NETWORK = "network"
    STORAGE = "storage"
    CLOUD = "cloud"
    KUBERNETES = "kubernetes"
    INDUSTRIAL = "industrial"
    PERFORMANCE = "performance"
    BACKUP = "backup"
    DISASTER_RECOVERY = "disaster_recovery"
    CUSTOM = "custom"


class ValidationTargetType(StrEnum):
    """Per docs/043's own "VALIDATION TARGETS" list (15 values,
    singularized from the doc's own plural section headings the same
    way every prior AI-IOS enum already singularizes its own section
    heading, e.g. ``NodeType.TASK`` from "Tasks").
    """

    PHYSICAL_SERVER = "physical_server"
    VIRTUAL_MACHINE = "virtual_machine"
    CONTAINER = "container"
    KUBERNETES = "kubernetes"
    APPLICATION = "application"
    DATABASE = "database"
    STORAGE = "storage"
    NETWORK_DEVICE = "network_device"
    CLOUD_RESOURCE = "cloud_resource"
    INDUSTRIAL_CONTROLLER = "industrial_controller"
    EDGE_DEVICE = "edge_device"
    AUTOMATION_JOB = "automation_job"
    WORKFLOW_EXECUTION = "workflow_execution"
    CONFIGURATION_PROFILE = "configuration_profile"
    CUSTOM_TARGET = "custom_target"


class ValidationProfileType(StrEnum):
    """Per docs/043's own "VALIDATION PROFILES" "Support" list (first 10
    entries -- "Reusable Templates"/"Versioning" from the same list are
    capabilities, not profile types, and are handled by the separate
    ``validation_templates`` table and ``ValidationProfile
    .current_version_number`` respectively).
    """

    INFRASTRUCTURE = "infrastructure"
    CLOUD = "cloud"
    KUBERNETES = "kubernetes"
    INDUSTRIAL = "industrial"
    SECURITY = "security"
    COMPLIANCE = "compliance"
    DEPLOYMENT = "deployment"
    HEALTH = "health"
    PERFORMANCE = "performance"
    CUSTOM = "custom"


class ValidationCheckType(StrEnum):
    """Per docs/043's own "VALIDATION CHECKS" "Support" list (19 values, verbatim)."""

    CONNECTIVITY = "connectivity"
    AUTHENTICATION = "authentication"
    CONFIGURATION = "configuration"
    SERVICES = "services"
    PORTS = "ports"
    DNS = "dns"
    CERTIFICATES = "certificates"
    DISK_USAGE = "disk_usage"
    CPU = "cpu"
    MEMORY = "memory"
    NETWORK = "network"
    STORAGE = "storage"
    PROCESSES = "processes"
    OPERATING_SYSTEM = "operating_system"
    KERNEL = "kernel"
    PACKAGES = "packages"
    SECURITY_POLICIES = "security_policies"
    COMPLIANCE_POLICIES = "compliance_policies"
    CUSTOM = "custom"


class ValidationTriggerType(StrEnum):
    """What caused a :class:`~app.models.validation_execution
    .ValidationExecution` to start.

    Per docs/043's own "EXECUTION MODES" list, minus its own final two
    entries ("Parallel Execution"/"Distributed Execution") -- those
    describe *how* an execution's own checks run relative to each
    other, an orthogonal concept to *why* it started, and are instead
    modeled as :class:`ValidationConcurrencyStrategy` (which also
    absorbs "VALIDATION ENGINE"'s own "Sequential Checks"/"Parallel
    Checks").
    """

    MANUAL = "manual"
    SCHEDULED = "scheduled"
    CONTINUOUS = "continuous"
    PRE_DEPLOYMENT = "pre_deployment"
    POST_DEPLOYMENT = "post_deployment"
    WORKFLOW_TRIGGERED = "workflow_triggered"
    AUTOMATION_TRIGGERED = "automation_triggered"
    API_TRIGGERED = "api_triggered"
    EVENT_TRIGGERED = "event_triggered"


class ValidationConcurrencyStrategy(StrEnum):
    """How an execution's own checks run relative to each other.

    Unifies two doc sections describing the same underlying concept at
    two different granularities: "EXECUTION MODES"' own "Parallel
    Execution"/"Distributed Execution" (target-level concurrency) and
    "VALIDATION ENGINE"'s own "Sequential Checks"/"Parallel Checks"
    (check-level concurrency) -- both boil down to "sequential, in
    one process" vs. "concurrent, in one process" vs. "spread across
    worker processes", so one enum serves
    ``ValidationExecution.concurrency_strategy`` at both levels rather
    than two near-duplicate enums. ``SEQUENTIAL`` is added as the
    implied default neither doc section states explicitly but every
    execution needs a value for.
    """

    SEQUENTIAL = "sequential"
    PARALLEL = "parallel"
    DISTRIBUTED = "distributed"


class ValidationResultStatus(StrEnum):
    """Per docs/043's own "RESULT STATUS" list (8 values, verbatim) --
    the outcome of one :class:`~app.models.validation_result
    .ValidationResult` (one check against one target within one
    execution).
    """

    PASSED = "passed"
    FAILED = "failed"
    WARNING = "warning"
    SKIPPED = "skipped"
    NOT_APPLICABLE = "not_applicable"
    TIMEOUT = "timeout"
    CANCELLED = "cancelled"
    UNKNOWN = "unknown"


class ValidationExecutionStatus(StrEnum):
    """The lifecycle status of a whole
    :class:`~app.models.validation_execution.ValidationExecution`.

    Not literally named in docs/043 (only "RESULT STATUS", covering a
    single check's own outcome, is) -- an execution needs its own
    in-flight states before any result exists at all. Reuses
    :class:`ValidationResultStatus`'s own terminal-outcome vocabulary
    (``PASSED``/``FAILED``/``WARNING``/``CANCELLED``/``TIMEOUT``/
    ``UNKNOWN``, each meaning "how did the aggregate of every check in
    this run turn out") prefixed with the two states that only make
    sense at the whole-execution level (``QUEUED``/``RUNNING``), and
    drops ``SKIPPED``/``NOT_APPLICABLE`` since an entire execution is
    never itself skipped or not-applicable the way one check can be.
    """

    QUEUED = "queued"
    RUNNING = "running"
    PASSED = "passed"
    FAILED = "failed"
    WARNING = "warning"
    CANCELLED = "cancelled"
    TIMEOUT = "timeout"
    UNKNOWN = "unknown"


class ValidationSeverity(StrEnum):
    """Not its own named list in docs/043, but required by "REMEDIATION"'s
    own severity-implying prioritization and "NOTIFICATIONS"' own
    "Critical Validation Failed" entry -- added directly the same
    "required concept, no literal list" precedent every prior AI-IOS
    service has established at least once. Backs
    ``ValidationRule.severity``/``ValidationFailure.severity`` and the
    weight a failure contributes to
    :class:`~app.models.validation_score.ValidationScore`.
    """

    INFO = "info"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class RemediationActionType(StrEnum):
    """Per docs/043's own "REMEDIATION" "Support" list (7 values, verbatim)."""

    RECOMMENDED_FIX = "recommended_fix"
    AUTOMATION_INTEGRATION = "automation_integration"
    KNOWLEDGE_BASE_LINK = "knowledge_base_link"
    PLAYBOOK_SUGGESTION = "playbook_suggestion"
    WORKFLOW_SUGGESTION = "workflow_suggestion"
    MANUAL_ACTION = "manual_action"
    AI_RECOMMENDATION_HOOK = "ai_recommendation_hook"


class ValidationReportType(StrEnum):
    """Per docs/043's own "REPORTING" "Generate" list (7 values, verbatim)."""

    VALIDATION = "validation"
    COMPLIANCE = "compliance"
    SECURITY = "security"
    EXECUTIVE = "executive"
    OPERATIONAL = "operational"
    TREND = "trend"
    ASSET = "asset"


class AuditOutcome(StrEnum):
    """Reused ``SUCCESS``/``FAILURE`` shape, the same convention every
    prior AI-IOS audit-trail table established.
    """

    SUCCESS = "success"
    FAILURE = "failure"


class ValidationExceptionStatus(StrEnum):
    """Not its own named list in docs/043, but required for the
    ``validation_exceptions`` table's own approval workflow (waiving a
    known failure) -- added directly via design reasoning, the same
    "required table, no literal enum list" precedent every prior
    AI-IOS service has established at least once.
    """

    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    EXPIRED = "expired"


__all__ = [
    "AuditOutcome",
    "RemediationActionType",
    "ValidationCheckType",
    "ValidationConcurrencyStrategy",
    "ValidationExceptionStatus",
    "ValidationExecutionStatus",
    "ValidationProfileType",
    "ValidationReportType",
    "ValidationResultStatus",
    "ValidationSeverity",
    "ValidationTargetType",
    "ValidationTriggerType",
    "ValidationType",
]
