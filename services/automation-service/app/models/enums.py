"""Enumerations for the automation service's persisted domain.

Per docs/040 "AUTOMATION TYPES"/"EXECUTION TARGETS"/"EXECUTION MODES"/
etc. Sections that enumerate concrete values verbatim are copied
exactly; sections that only name a field or a "Support"/"Capture"/
"Collect" capability list (without a value enumeration) are given a
small, conventional value set documented as derived in that enum's own
docstring -- the same precedent
``services/configuration-management-service``'s own ``app/models
/enums.py`` established.
"""

from __future__ import annotations

from enum import StrEnum


class AutomationType(StrEnum):
    """Per docs/040 "AUTOMATION TYPES" (20 values, verbatim)."""

    INFRASTRUCTURE_AUTOMATION = "infrastructure_automation"
    CONFIGURATION_AUTOMATION = "configuration_automation"
    PROVISIONING = "provisioning"
    DECOMMISSIONING = "decommissioning"
    DEPLOYMENT = "deployment"
    PATCH_MANAGEMENT = "patch_management"
    SOFTWARE_INSTALLATION = "software_installation"
    FIRMWARE_UPGRADE = "firmware_upgrade"
    OS_CONFIGURATION = "os_configuration"
    VALIDATION_EXECUTION = "validation_execution"
    DISCOVERY_EXECUTION = "discovery_execution"
    MONITORING_ACTIONS = "monitoring_actions"
    DATABASE_AUTOMATION = "database_automation"
    CLOUD_AUTOMATION = "cloud_automation"
    CONTAINER_AUTOMATION = "container_automation"
    KUBERNETES_AUTOMATION = "kubernetes_automation"
    INDUSTRIAL_AUTOMATION = "industrial_automation"
    SECURITY_AUTOMATION = "security_automation"
    BACKUP_AUTOMATION = "backup_automation"
    CUSTOM_AUTOMATION = "custom_automation"


class ExecutionTargetType(StrEnum):
    """Per docs/040 "EXECUTION TARGETS" (15 values, verbatim)."""

    PHYSICAL_SERVER = "physical_server"
    VIRTUAL_MACHINE = "virtual_machine"
    CONTAINER = "container"
    KUBERNETES = "kubernetes"
    CLOUD_RESOURCE = "cloud_resource"
    STORAGE_SYSTEM = "storage_system"
    SWITCH = "switch"
    ROUTER = "router"
    FIREWALL = "firewall"
    INDUSTRIAL_CONTROLLER = "industrial_controller"
    APPLICATION = "application"
    DATABASE = "database"
    CUSTOM_TARGET = "custom_target"
    TARGET_GROUP = "target_group"
    DYNAMIC_INVENTORY = "dynamic_inventory"


class ExecutionMode(StrEnum):
    """Per docs/040 "EXECUTION MODES" (9 values, verbatim)."""

    IMMEDIATE = "immediate"
    SCHEDULED = "scheduled"
    WORKFLOW_TRIGGERED = "workflow_triggered"
    EVENT_TRIGGERED = "event_triggered"
    WEBHOOK_TRIGGERED = "webhook_triggered"
    API_TRIGGERED = "api_triggered"
    MANUAL = "manual"
    APPROVAL_REQUIRED = "approval_required"
    CONTINUOUS = "continuous"


class PlaybookType(StrEnum):
    """Per docs/040 "PLAYBOOK SUPPORT" (9 values, verbatim). No runner is
    registered for ``FUTURE_DSL`` -- docs/040 itself names it "Future
    DSL Support", not a present-tense capability; dispatching to it
    raises a clear, real error rather than a placeholder implementation.
    """

    ANSIBLE_PLAYBOOK = "ansible_playbook"
    PYTHON_SCRIPT = "python_script"
    SHELL_SCRIPT = "shell_script"
    POWERSHELL = "powershell"
    BASH = "bash"
    TOSCA_SERVICE_TEMPLATE = "tosca_service_template"
    CUSTOM_PLUGIN = "custom_plugin"
    WORKFLOW_TASK = "workflow_task"
    FUTURE_DSL = "future_dsl"


class JobStatus(StrEnum):
    """Derived from docs/040 "AUTOMATION CRUD"'s own enable/disable
    lifecycle for a reusable job *definition* (distinct from one
    particular run's own :class:`ExecutionStatus`), the same
    definition/run status split
    ``services/configuration-management-service``'s own
    ``ProfileStatus``/``ConfigurationAssignmentStatus`` pair established.
    """

    DRAFT = "draft"
    ACTIVE = "active"
    DISABLED = "disabled"
    ARCHIVED = "archived"


class ExecutionStatus(StrEnum):
    """Derived from docs/040 "EVENTS" own lifecycle verbs
    (``AutomationStarted``/``Completed``/``Failed``/``Cancelled``/
    ``Paused``/``Resumed``, ``ExecutionTimedOut``) plus "ROLLBACK"'s own
    outcome, converted to the states they leave an execution in --
    the same "derive states from named action verbs" precedent
    ``services/asset-management-service``'s own ``LifecycleState``
    established for an analogous gap.
    """

    PENDING = "pending"
    RUNNING = "running"
    PAUSED = "paused"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    TIMED_OUT = "timed_out"
    ROLLED_BACK = "rolled_back"


class ExecutionStepStatus(StrEnum):
    """Derived from docs/040 "EXECUTION PLANS" own step lifecycle
    (Pre-check/Preparation/Validation/Execution/Post-validation/
    Cleanup), which implies a per-step status without enumerating one.
    """

    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"
    ROLLED_BACK = "rolled_back"


class LogLevel(StrEnum):
    """Derived from docs/040 "LOGGING" "Capture" ("Errors", "Warnings"),
    which implies a severity level without enumerating one -- the
    standard four-level convention already used by
    ``shared_core.logging`` itself.
    """

    DEBUG = "debug"
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"


class ConnectorType(StrEnum):
    """Per docs/040 "CONNECTOR INTEGRATION" "Support" (11 values,
    verbatim). Only :data:`ConnectorType.SSH` has a concrete
    ``shared_core.connectors.BaseConnector`` provider registered by
    this service (live-tested against a real Docker SSH container);
    every other member is real, storable target metadata that
    dispatches through the same ``ConnectorRegistry`` lookup and raises
    a clear ``DependencyError`` if attempted, matching
    ``packages/shared-core/connectors``' own explicit, user-confirmed
    scope note that concrete provider packages beyond the core SDK are
    a separate, later phase of work.
    """

    SSH = "ssh"
    WINRM = "winrm"
    REDFISH = "redfish"
    SNMP = "snmp"
    REST = "rest"
    GRPC = "grpc"
    VMWARE = "vmware"
    KUBERNETES = "kubernetes"
    CLOUD_PROVIDER = "cloud_provider"
    INDUSTRIAL_PROTOCOL = "industrial_protocol"
    PLUGIN_CONNECTOR = "plugin_connector"


class ApprovalType(StrEnum):
    """Per docs/040 "APPROVALS" "Support" (5 values, verbatim; "Approval
    Expiration"/"Approval History" describe behavior, not a type of
    their own).
    """

    SINGLE = "single"
    MULTI_LEVEL = "multi_level"
    CONDITIONAL = "conditional"
    ROLE_BASED = "role_based"
    EMERGENCY_OVERRIDE = "emergency_override"


class ApprovalStatus(StrEnum):
    """Derived from docs/040 "APPROVALS" "Support" ("Approval
    Expiration", "Rejection" implied by any approval gate), the same
    lifecycle shape
    ``services/configuration-management-service``'s own
    ``ApprovalStatus`` established.
    """

    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    EXPIRED = "expired"


class RetryStrategy(StrEnum):
    """Per docs/040 "RETRY" "Support" (3 values, verbatim; "Retry
    Policies"/"Retry Limits"/"Failure Classification" describe
    behavior, not a strategy of their own).
    """

    IMMEDIATE = "immediate"
    DELAYED = "delayed"
    EXPONENTIAL_BACKOFF = "exponential_backoff"


class FailureClassification(StrEnum):
    """Derived from docs/040 "RETRY" "Failure Classification", which
    names the capability without enumerating its own outcome values.
    """

    TRANSIENT = "transient"
    PERMANENT = "permanent"
    TIMEOUT = "timeout"
    AUTHENTICATION = "authentication"
    UNKNOWN = "unknown"


class RollbackType(StrEnum):
    """Per docs/040 "ROLLBACK" "Support" (6 values, verbatim;
    "Rollback Validation"/"Rollback Reports" describe behavior/
    artifacts, not a type of their own).
    """

    STEP = "step"
    EXECUTION = "execution"
    CONFIGURATION = "configuration"
    PLAYBOOK = "playbook"
    AUTOMATIC = "automatic"
    MANUAL = "manual"


class RollbackStatus(StrEnum):
    """Derived from docs/040 "ROLLBACK" "Support", the same
    pending/in-progress/completed/failed lifecycle shape
    ``services/configuration-management-service``'s own
    ``RollbackStatus`` established.
    """

    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"


class ArtifactType(StrEnum):
    """Per docs/040 "ARTIFACTS" "Store" (7 values, verbatim)."""

    EXECUTION_REPORT = "execution_report"
    GENERATED_FILE = "generated_file"
    PLAYBOOK_OUTPUT = "playbook_output"
    LOG = "log"
    CONFIGURATION_SNAPSHOT = "configuration_snapshot"
    VALIDATION_RESULT = "validation_result"
    ATTACHMENT = "attachment"


class AutomationReportType(StrEnum):
    """Per docs/040 "REPORTING" "Generate" (7 values, verbatim)."""

    EXECUTION = "execution"
    FAILURE = "failure"
    SUCCESS = "success"
    PERFORMANCE = "performance"
    COMPLIANCE = "compliance"
    EXECUTIVE_DASHBOARD = "executive_dashboard"
    AUTOMATION_TRENDS = "automation_trends"


class VariableScope(StrEnum):
    """Derived from docs/040 "WORKFLOW INTEGRATION" "Shared Variables"
    plus "AUTOMATION VARIABLES"-shaped need to scope a variable beyond
    one execution, mirroring
    ``services/configuration-management-service``'s own
    ``VariableScope`` shape (a subset relevant to this service: no
    ``SECRET_REFERENCE``/``RUNTIME``/``COMPUTED`` split of its own,
    since :attr:`~app.models.automation_variable.AutomationVariable
    .is_secret_reference` already covers that distinction as a flag).
    """

    GLOBAL = "global"
    ORGANIZATION = "organization"
    PROJECT = "project"
    JOB = "job"
    EXECUTION = "execution"


class AuditOutcome(StrEnum):
    """Reused ``SUCCESS``/``FAILURE`` shape, the same convention every
    prior AI-IOS service's own audit-trail enum established.
    """

    SUCCESS = "success"
    FAILURE = "failure"


__all__ = [
    "ApprovalStatus",
    "ApprovalType",
    "ArtifactType",
    "AuditOutcome",
    "AutomationReportType",
    "AutomationType",
    "ConnectorType",
    "ExecutionMode",
    "ExecutionStatus",
    "ExecutionStepStatus",
    "ExecutionTargetType",
    "FailureClassification",
    "JobStatus",
    "LogLevel",
    "PlaybookType",
    "RetryStrategy",
    "RollbackStatus",
    "RollbackType",
    "VariableScope",
]
