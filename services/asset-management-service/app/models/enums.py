"""Enumerations for the asset management service's persisted domain.

Per docs/038 "MANAGED ASSET MODEL"/"ASSET STATUS"/etc. Sections that
enumerate concrete values verbatim are copied exactly; sections that
only name a field or a "Support"/"Track"/"Evaluate" capability list
(without a value enumeration) are given a small, conventional value
set documented as derived in that enum's own docstring -- following
the same precedent set by inventory-service's own ``Criticality``.
"""

from __future__ import annotations

from enum import StrEnum


class ManagedAssetStatus(StrEnum):
    """Per docs/038 "ASSET STATUS" (11 values, verbatim)."""

    PLANNED = "planned"
    ORDERED = "ordered"
    PROVISIONING = "provisioning"
    OPERATIONAL = "operational"
    MAINTENANCE = "maintenance"
    STANDBY = "standby"
    SUSPENDED = "suspended"
    RETIRED = "retired"
    DISPOSED = "disposed"
    ARCHIVED = "archived"
    DELETED = "deleted"


class Criticality(StrEnum):
    """Per docs/038 "CRITICALITY" (5 values, verbatim)."""

    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    INFORMATIONAL = "informational"


class LifecycleState(StrEnum):
    """Per docs/038 "LIFECYCLE MANAGEMENT" "Support" (8 actions:
    Provision/Operate/Maintain/Upgrade/Reassign/Retire/Archive/Dispose)
    -- converted to the state a managed asset is left in after each
    action, since the MANAGED ASSET MODEL's own "Lifecycle State"
    field is distinct from "Status" but docs/038 gives no separate
    noun-form value list for it. Deliberately overlaps some
    ``ManagedAssetStatus`` values (e.g. ``RETIRED``), matching
    inventory-service's own Status/LifecycleState overlap.
    """

    PROVISIONING = "provisioning"
    OPERATIONAL = "operational"
    MAINTENANCE = "maintenance"
    UPGRADING = "upgrading"
    REASSIGNING = "reassigning"
    RETIRED = "retired"
    ARCHIVED = "archived"
    DISPOSED = "disposed"


class WarrantyStatus(StrEnum):
    """MANAGED ASSET MODEL names "Warranty Status" as a required field
    without enumerating values; derived from the WARRANTY section's
    "Expiration Alerts" capability.
    """

    ACTIVE = "active"
    EXPIRING_SOON = "expiring_soon"
    EXPIRED = "expired"
    VOID = "void"
    UNKNOWN = "unknown"


class RenewalStatus(StrEnum):
    """Per docs/038 WARRANTY "Renewal Status" and CONTRACT MANAGEMENT
    "Renewal Tracking" -- both name renewal tracking without
    enumerating values; this single enum backs both.
    """

    NOT_RENEWED = "not_renewed"
    PENDING = "pending"
    RENEWED = "renewed"
    DECLINED = "declined"


class ComplianceStatus(StrEnum):
    """MANAGED ASSET MODEL names "Compliance Status" as a required
    field without enumerating values; derived from the COMPLIANCE
    section's "Exceptions" capability.
    """

    COMPLIANT = "compliant"
    NON_COMPLIANT = "non_compliant"
    PARTIALLY_COMPLIANT = "partially_compliant"
    EXCEPTION = "exception"
    UNKNOWN = "unknown"


class OperationalHealth(StrEnum):
    """MANAGED ASSET MODEL names "Operational Health" as a required
    field without enumerating values; the standard four-tier scale
    used by HEALTH MANAGEMENT's own "Health Score"/"Health Trends"
    aggregation.
    """

    HEALTHY = "healthy"
    WARNING = "warning"
    CRITICAL = "critical"
    UNKNOWN = "unknown"


class OwnerRole(StrEnum):
    """Per docs/038 "OWNERSHIP" "Support" -- the roles that name a
    responsible party rather than a reachable contact (the "Vendor
    Contact"/"Escalation Contact" pair below is split into
    :class:`ContactRole` for the separate ``asset_contacts`` table).
    """

    BUSINESS_OWNER = "business_owner"
    TECHNICAL_OWNER = "technical_owner"
    APPLICATION_OWNER = "application_owner"
    INFRASTRUCTURE_OWNER = "infrastructure_owner"
    DEPARTMENT = "department"
    SUPPORT_TEAM = "support_team"


class ContactRole(StrEnum):
    """Per docs/038 "OWNERSHIP" "Support" -- the two roles that name a
    reachable contact rather than a responsible owner. See
    :class:`OwnerRole`.
    """

    VENDOR_CONTACT = "vendor_contact"
    ESCALATION_CONTACT = "escalation_contact"


class AssignmentType(StrEnum):
    """Per docs/038 "ASSIGNMENTS" "Support" (Assign Asset/Bulk
    Assignment/Temporary Assignment, verbatim-derived); "Reassign
    Asset" is the same assignment type re-applied, not a distinct
    type of its own.
    """

    STANDARD = "standard"
    TEMPORARY = "temporary"
    BULK = "bulk"


class AssignmentStatus(StrEnum):
    """Derived from docs/038 "ASSIGNMENTS" "Support" "Assignment
    Approval" workflow, which implies a pending/active/returned
    lifecycle without enumerating it.
    """

    PENDING_APPROVAL = "pending_approval"
    ACTIVE = "active"
    RETURNED = "returned"
    CANCELLED = "cancelled"


class ContractType(StrEnum):
    """Per docs/038 "CONTRACT MANAGEMENT" "Support" (Support/
    Maintenance/License/Vendor Contracts, verbatim-derived)."""

    SUPPORT = "support"
    MAINTENANCE = "maintenance"
    LICENSE = "license"
    VENDOR = "vendor"


class ContractStatus(StrEnum):
    """Derived from docs/038 "CONTRACT MANAGEMENT" "Contract
    Expiration"/"Renewal Tracking", which imply a lifecycle without
    enumerating it.
    """

    PENDING = "pending"
    ACTIVE = "active"
    RENEWED = "renewed"
    EXPIRED = "expired"
    CANCELLED = "cancelled"


class DepreciationMethod(StrEnum):
    """Per docs/038 "DEPRECIATION" "Support" (4 values, verbatim)."""

    STRAIGHT_LINE = "straight_line"
    DECLINING_BALANCE = "declining_balance"
    UNITS_OF_PRODUCTION = "units_of_production"
    CUSTOM = "custom"


class CostType(StrEnum):
    """Per docs/038 "COST MANAGEMENT" "Track" (9 values, verbatim;
    "Total Cost of Ownership (TCO)" is a computed aggregate over these
    rather than a cost type of its own).
    """

    ACQUISITION = "acquisition"
    OPERATIONAL = "operational"
    MAINTENANCE = "maintenance"
    SUPPORT = "support"
    ENERGY = "energy"
    CLOUD = "cloud"
    SUBSCRIPTION = "subscription"
    REPAIR = "repair"
    REPLACEMENT = "replacement"


class MaintenanceType(StrEnum):
    """Per docs/038 "MAINTENANCE" "Support" (4 values, verbatim)."""

    SCHEDULED = "scheduled"
    EMERGENCY = "emergency"
    PREVENTIVE = "preventive"
    CORRECTIVE = "corrective"


class MaintenanceStatus(StrEnum):
    """Derived from docs/038 "MAINTENANCE" "Approval Workflow" and
    "MAINTENANCE WINDOWS" "Execution History", which imply a
    scheduled/in-progress/completed lifecycle without enumerating it.
    """

    SCHEDULED = "scheduled"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    CANCELLED = "cancelled"
    OVERDUE = "overdue"


class MaintenanceWindowType(StrEnum):
    """Per docs/038 "MAINTENANCE WINDOWS" "Support" (2 values,
    verbatim).
    """

    RECURRING = "recurring"
    ONE_TIME = "one_time"


class SoftwareEndOfLifeStatus(StrEnum):
    """SOFTWARE MANAGEMENT names "End-of-Life Status" as a tracked
    field without enumerating values.
    """

    SUPPORTED = "supported"
    END_OF_LIFE = "end_of_life"
    END_OF_SUPPORT = "end_of_support"
    UNKNOWN = "unknown"


class ComplianceType(StrEnum):
    """Per docs/038 "COMPLIANCE" "Support" (6 values, verbatim;
    "Internal Policies" renamed to the singular ``INTERNAL_POLICY``
    for enum-member convention).
    """

    SECURITY = "security"
    CONFIGURATION = "configuration"
    LICENSE = "license"
    PATCH = "patch"
    INDUSTRY = "industry"
    INTERNAL_POLICY = "internal_policy"


class RiskType(StrEnum):
    """Per docs/038 "RISK MANAGEMENT" "Evaluate" (5 values,
    verbatim).
    """

    OPERATIONAL = "operational"
    SECURITY = "security"
    BUSINESS = "business"
    VENDOR = "vendor"
    COMPLIANCE = "compliance"


class RiskLevel(StrEnum):
    """Derived categorical banding for the numeric "Risk Score" named
    by both MANAGED ASSET MODEL and RISK MANAGEMENT "Risk Scoring".
    """

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class ReportType(StrEnum):
    """Per docs/038 "REPORTING" "Generate" (8 values, verbatim)."""

    ASSET = "asset"
    COST = "cost"
    COMPLIANCE = "compliance"
    WARRANTY = "warranty"
    MAINTENANCE = "maintenance"
    RISK = "risk"
    LIFECYCLE = "lifecycle"
    EXECUTIVE_DASHBOARD = "executive_dashboard"


class AnalyticsMetric(StrEnum):
    """Per docs/038 "ANALYTICS" "Collect" (8 values, verbatim)."""

    ASSET_GROWTH = "asset_growth"
    OPERATIONAL_HEALTH = "operational_health"
    MAINTENANCE_TRENDS = "maintenance_trends"
    COMPLIANCE_TRENDS = "compliance_trends"
    RISK_TRENDS = "risk_trends"
    COST_TRENDS = "cost_trends"
    VENDOR_PERFORMANCE = "vendor_performance"
    LIFECYCLE_DISTRIBUTION = "lifecycle_distribution"


class AuditOutcome(StrEnum):
    """Whether an audited administrative action succeeded or failed."""

    SUCCESS = "success"
    FAILURE = "failure"


__all__ = [
    "AnalyticsMetric",
    "AssignmentStatus",
    "AssignmentType",
    "AuditOutcome",
    "ComplianceStatus",
    "ComplianceType",
    "ContactRole",
    "ContractStatus",
    "ContractType",
    "CostType",
    "Criticality",
    "DepreciationMethod",
    "LifecycleState",
    "MaintenanceStatus",
    "MaintenanceType",
    "MaintenanceWindowType",
    "ManagedAssetStatus",
    "OperationalHealth",
    "OwnerRole",
    "RenewalStatus",
    "ReportType",
    "RiskLevel",
    "RiskType",
    "SoftwareEndOfLifeStatus",
    "WarrantyStatus",
]
