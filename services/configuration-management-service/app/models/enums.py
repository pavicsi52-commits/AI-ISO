"""Enumerations for the configuration management service's persisted
domain.

Per docs/039 "CONFIGURATION PROFILE MODEL"/"PROFILE STATUS"/etc.
Sections that enumerate concrete values verbatim are copied exactly;
sections that only name a field or a "Support"/"Evaluate"/"Detect"
capability list (without a value enumeration) are given a small,
conventional value set documented as derived in that enum's own
docstring -- the same precedent
``services/asset-management-service``'s own ``app/models/enums.py``
established.
"""

from __future__ import annotations

from enum import StrEnum


class ProfileStatus(StrEnum):
    """Per docs/039 "PROFILE STATUS" (7 values, verbatim)."""

    DRAFT = "draft"
    PENDING_APPROVAL = "pending_approval"
    APPROVED = "approved"
    ACTIVE = "active"
    DEPRECATED = "deprecated"
    ARCHIVED = "archived"
    DELETED = "deleted"


class ConfigurationType(StrEnum):
    """Per docs/039 "CONFIGURATION TYPES" (15 values, verbatim)."""

    INFRASTRUCTURE = "infrastructure"
    OPERATING_SYSTEM = "operating_system"
    APPLICATION = "application"
    DATABASE = "database"
    NETWORK = "network"
    STORAGE = "storage"
    CLOUD = "cloud"
    KUBERNETES = "kubernetes"
    CONTAINER = "container"
    INDUSTRIAL = "industrial"
    SECURITY = "security"
    MONITORING = "monitoring"
    AUTOMATION = "automation"
    VALIDATION = "validation"
    CUSTOM = "custom"


class EnvironmentType(StrEnum):
    """Per docs/039 "ENVIRONMENTS" "Support" (9 values, verbatim)."""

    DEVELOPMENT = "development"
    TESTING = "testing"
    QA = "qa"
    STAGING = "staging"
    PRODUCTION = "production"
    DISASTER_RECOVERY = "disaster_recovery"
    EDGE = "edge"
    INDUSTRIAL = "industrial"
    CUSTOM = "custom"


class BaselineType(StrEnum):
    """Per docs/039 "BASELINES" "Support" (7 values, verbatim)."""

    GOLDEN_IMAGE = "golden_image"
    GOLDEN_CONFIGURATION = "golden_configuration"
    COMPLIANCE_BASELINE = "compliance_baseline"
    SECURITY_BASELINE = "security_baseline"
    PERFORMANCE_BASELINE = "performance_baseline"
    VENDOR_BASELINE = "vendor_baseline"
    CUSTOM_BASELINE = "custom_baseline"


class VariableScope(StrEnum):
    """Per docs/039 "CONFIGURATION VARIABLES" "Support" (8 values,
    verbatim; "Validation Rules" is a per-variable capability, not a
    scope of its own, so it is not a member here).
    """

    GLOBAL = "global"
    ORGANIZATION = "organization"
    PROJECT = "project"
    ENVIRONMENT = "environment"
    ASSET = "asset"
    SECRET_REFERENCE = "secret_reference"
    RUNTIME = "runtime"
    COMPUTED = "computed"


class ConfigurationAssignmentStatus(StrEnum):
    """MANAGED ASSET MODEL's own "Target Assets"/"ConfigurationAssigned"
    naming implies an assignment lifecycle without enumerating it.
    """

    ACTIVE = "active"
    PENDING = "pending"
    FAILED = "failed"
    REMOVED = "removed"


class DriftType(StrEnum):
    """Per docs/039 "DRIFT DETECTION" "Detect" (7 values, verbatim)."""

    MISSING_CONFIGURATION = "missing_configuration"
    UNEXPECTED_CHANGES = "unexpected_changes"
    UNAUTHORIZED_CHANGES = "unauthorized_changes"
    VERSION_DRIFT = "version_drift"
    POLICY_DRIFT = "policy_drift"
    TEMPLATE_DRIFT = "template_drift"
    VARIABLE_DRIFT = "variable_drift"


class DriftStatus(StrEnum):
    """Derived from docs/039 "DRIFT DETECTION"'s own detect-then-resolve
    lifecycle, which implies a status without enumerating it.
    """

    DETECTED = "detected"
    ACKNOWLEDGED = "acknowledged"
    RESOLVED = "resolved"
    IGNORED = "ignored"


class ComplianceEvalType(StrEnum):
    """Per docs/039 "COMPLIANCE" "Evaluate" (6 values, verbatim)."""

    SECURITY = "security"
    CONFIGURATION = "configuration"
    BASELINE = "baseline"
    POLICY = "policy"
    ENVIRONMENT = "environment"
    INDUSTRY_STANDARDS = "industry_standards"


class ComplianceStatus(StrEnum):
    """Derived -- docs/039 names no explicit outcome value list for
    "COMPLIANCE" "Evaluate", the same gap
    ``services/asset-management-service``'s own ``ComplianceStatus``
    already had to fill for an analogous section.
    """

    COMPLIANT = "compliant"
    NON_COMPLIANT = "non_compliant"
    PARTIALLY_COMPLIANT = "partially_compliant"
    EXCEPTION = "exception"
    UNKNOWN = "unknown"


class BackupType(StrEnum):
    """Per docs/039 "BACKUP" "Support" (3 values, verbatim)."""

    CONFIGURATION_BACKUP = "configuration_backup"
    SNAPSHOT = "snapshot"
    EXPORT = "export"


class BackupStatus(StrEnum):
    """Derived from docs/039 "BACKUP" "Integrity Verification", which
    implies a pending/verified lifecycle without enumerating it.
    """

    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"


class RestoreType(StrEnum):
    """Per docs/039 "RESTORE" "Support" (5 values, verbatim-derived)."""

    PROFILE = "profile"
    VERSION = "version"
    SELECTIVE = "selective"
    BULK = "bulk"
    PREVIEW = "preview"


class RestoreStatus(StrEnum):
    """Derived from docs/039 "RESTORE" "Validation"/"Audit", which
    imply a lifecycle without enumerating it.
    """

    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"


class RollbackType(StrEnum):
    """Per docs/039 "ROLLBACK" "Support" (3 values, verbatim)."""

    VERSION = "version"
    INCREMENTAL = "incremental"
    FULL = "full"


class RollbackStatus(StrEnum):
    """Derived from docs/039 "ROLLBACK" "Approval Workflow", which
    implies a pending/approved/applied lifecycle without enumerating it.
    """

    PENDING = "pending"
    APPROVED = "approved"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"


class ChangeSetStatus(StrEnum):
    """Derived -- docs/039 "VERSIONING" "Change Tracking" implies a
    draft/applied lifecycle for a grouped set of changes without
    enumerating it.
    """

    DRAFT = "draft"
    APPLIED = "applied"
    REVERTED = "reverted"


class GitProvider(StrEnum):
    """Per docs/039 "GITOPS" "Support" (5 values, verbatim)."""

    GITHUB = "github"
    GITLAB = "gitlab"
    AZURE_DEVOPS = "azure_devops"
    BITBUCKET = "bitbucket"
    GITEA = "gitea"


class GitSyncStatus(StrEnum):
    """Derived from docs/039 "GITOPS" "Synchronization"/"Conflict
    Detection", which imply a sync lifecycle without enumerating it.
    """

    SYNCED = "synced"
    PENDING = "pending"
    CONFLICT = "conflict"
    ERROR = "error"


class ToscaComponentType(StrEnum):
    """Per docs/039 "TOSCA INTEGRATION" "Integrate" (7 values,
    verbatim; "TOSCA Templates" itself names the table's own concept,
    not a distinct component type).
    """

    CSAR_PACKAGE = "csar_package"
    NODE_TEMPLATE = "node_template"
    RELATIONSHIP_TEMPLATE = "relationship_template"
    POLICY = "policy"
    SUBSTITUTION_MAPPING = "substitution_mapping"
    ARTIFACT = "artifact"
    SERVICE_TEMPLATE = "service_template"


class ManifestFormat(StrEnum):
    """Per docs/039 "KUBERNETES" "Support" (3 values, verbatim)."""

    YAML_MANIFEST = "yaml_manifest"
    HELM_CHART = "helm_chart"
    KUSTOMIZE = "kustomize"


class PolicyType(StrEnum):
    """Per docs/039 "POLICIES" "Support" (7 values, verbatim)."""

    NAMING = "naming"
    VERSION = "version"
    APPROVAL = "approval"
    COMPLIANCE = "compliance"
    DEPLOYMENT = "deployment"
    RETENTION = "retention"
    ENVIRONMENT = "environment"


class ApprovalStatus(StrEnum):
    """Derived from docs/039 "APPROVALS" "Support" ("Rejection",
    "Resubmission"), which imply a lifecycle without enumerating it.
    """

    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    RESUBMITTED = "resubmitted"


class ConfigReportType(StrEnum):
    """Per docs/039 "REPORTING" "Generate" (7 values, verbatim)."""

    CONFIGURATION = "configuration"
    COMPLIANCE = "compliance"
    DRIFT = "drift"
    BASELINE = "baseline"
    VERSION = "version"
    APPROVAL = "approval"
    EXECUTIVE_DASHBOARD = "executive_dashboard"


class AuditOutcome(StrEnum):
    """Whether an audited administrative action succeeded or failed."""

    SUCCESS = "success"
    FAILURE = "failure"


__all__ = [
    "ApprovalStatus",
    "AuditOutcome",
    "BackupStatus",
    "BackupType",
    "BaselineType",
    "ChangeSetStatus",
    "ComplianceEvalType",
    "ComplianceStatus",
    "ConfigReportType",
    "ConfigurationAssignmentStatus",
    "ConfigurationType",
    "DriftStatus",
    "DriftType",
    "EnvironmentType",
    "GitProvider",
    "GitSyncStatus",
    "ManifestFormat",
    "PolicyType",
    "ProfileStatus",
    "RestoreStatus",
    "RestoreType",
    "RollbackStatus",
    "RollbackType",
    "ToscaComponentType",
    "VariableScope",
]
