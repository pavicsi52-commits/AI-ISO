"""The policy engine's vocabulary.

Every enum docs/050 names, as ``StrEnum`` so a value is its own wire
representation and a stored column is readable without a join.

**The effect ordering is the single most important thing in this file.**
:data:`EFFECT_PRECEDENCE` decides what happens when two policies match
one request and disagree, and getting it wrong is not a bug that shows
up as an error -- it is a bug that shows up as an authorization that
should not have been granted.
"""

from __future__ import annotations

from enum import StrEnum


class PolicyCategory(StrEnum):
    """What domain a policy governs (docs/050 "POLICY CATEGORIES")."""

    AUTHORIZATION = "authorization"
    AUTOMATION = "automation"
    WORKFLOW = "workflow"
    CONFIGURATION = "configuration"
    VALIDATION = "validation"
    MONITORING = "monitoring"
    ALERTING = "alerting"
    DASHBOARD = "dashboard"
    REPORTING = "reporting"
    KNOWLEDGE_GRAPH = "knowledge_graph"
    AI_ASSISTANT = "ai_assistant"
    SECRETS = "secrets"
    API_GATEWAY = "api_gateway"
    ORGANIZATION = "organization"
    PROJECT = "project"
    INFRASTRUCTURE = "infrastructure"
    COMPLIANCE = "compliance"
    SECURITY = "security"
    QUOTA = "quota"
    CUSTOM = "custom"


class PolicyType(StrEnum):
    """How a policy decides (docs/050 "POLICY TYPES")."""

    RBAC = "rbac"
    ABAC = "abac"
    CONTEXT_AWARE = "context_aware"
    APPROVAL = "approval"
    QUOTA = "quota"
    TIME_BASED = "time_based"
    ENVIRONMENT_BASED = "environment_based"
    RESOURCE_BASED = "resource_based"
    RISK_BASED = "risk_based"
    COMPLIANCE = "compliance"
    CUSTOM = "custom"


class SubjectType(StrEnum):
    """Who is asking (docs/050 "SUBJECTS")."""

    USER = "user"
    TEAM = "team"
    ROLE = "role"
    ORGANIZATION = "organization"
    PROJECT = "project"
    APPLICATION = "application"
    SERVICE = "service"
    API_CLIENT = "api_client"
    AUTOMATION_JOB = "automation_job"
    WORKFLOW = "workflow"
    AI_AGENT = "ai_agent"
    CUSTOM_SUBJECT = "custom_subject"


class ResourceType(StrEnum):
    """What is being acted on (docs/050 "RESOURCES")."""

    INFRASTRUCTURE_ASSET = "infrastructure_asset"
    CONFIGURATION_PROFILE = "configuration_profile"
    AUTOMATION_JOB = "automation_job"
    PLAYBOOK = "playbook"
    VALIDATION_PROFILE = "validation_profile"
    MONITORING_TARGET = "monitoring_target"
    DASHBOARD = "dashboard"
    REPORT = "report"
    KNOWLEDGE_GRAPH = "knowledge_graph"
    SECRET = "secret"
    PROJECT = "project"
    ORGANIZATION = "organization"
    CUSTOM_RESOURCE = "custom_resource"


class ActionType(StrEnum):
    """What is being attempted (docs/050 "ACTIONS")."""

    READ = "read"
    CREATE = "create"
    UPDATE = "update"
    DELETE = "delete"
    EXECUTE = "execute"
    APPROVE = "approve"
    REJECT = "reject"
    DEPLOY = "deploy"
    ROLLBACK = "rollback"
    IMPORT = "import"
    EXPORT = "export"
    SHARE = "share"
    MANAGE = "manage"
    CUSTOM_ACTION = "custom_action"


class PolicyEffect(StrEnum):
    """What one policy says to do (docs/050 "POLICY EVALUATION")."""

    ALLOW = "allow"
    DENY = "deny"
    CONDITIONAL_ALLOW = "conditional_allow"
    CONDITIONAL_DENY = "conditional_deny"
    REQUIRE_APPROVAL = "require_approval"
    REQUIRE_MFA = "require_mfa"
    ESCALATE = "escalate"
    QUOTA_EXCEEDED = "quota_exceeded"
    DEFERRED = "deferred"


EFFECT_PRECEDENCE: dict[PolicyEffect, int] = {
    PolicyEffect.ALLOW: 0,
    PolicyEffect.CONDITIONAL_ALLOW: 1,
    PolicyEffect.REQUIRE_MFA: 2,
    PolicyEffect.REQUIRE_APPROVAL: 3,
    PolicyEffect.ESCALATE: 4,
    PolicyEffect.DEFERRED: 5,
    PolicyEffect.QUOTA_EXCEEDED: 6,
    PolicyEffect.CONDITIONAL_DENY: 7,
    PolicyEffect.DENY: 8,
}
"""How two matching policies are combined: **the higher rank wins.**

This is deny-overrides, and the ordering between the middle values is
what makes it safe rather than merely conventional:

- ``DENY`` outranks everything. A single explicit deny cannot be
  outvoted by any number of allows, however specific they are. The
  alternative -- most-specific-wins -- means adding a narrow allow can
  silently punch a hole through a broad organizational deny, which is
  exactly the mistake nobody notices until an audit.
- **Friction outranks permission.** ``REQUIRE_APPROVAL`` beats
  ``REQUIRE_MFA`` beats ``CONDITIONAL_ALLOW``, so when one policy says
  "allow" and another says "only with approval", the caller gets the
  approval requirement. Combining in the other direction would let any
  broad allow policy erase every approval gate in the estate.
- ``QUOTA_EXCEEDED`` sits just under the denies because it *is* a
  refusal, but one whose reason is worth distinguishing: "you are out of
  budget" and "you are not permitted" need different responses from the
  caller, and collapsing them into one loses that.
- ``DEFERRED`` outranks the approval effects because a decision that
  could not be reached must never be reported as one that was. Failing
  open here would make an unreachable attribute source a silent grant.
"""

DENYING_EFFECTS: frozenset[PolicyEffect] = frozenset(
    {PolicyEffect.DENY, PolicyEffect.CONDITIONAL_DENY, PolicyEffect.QUOTA_EXCEEDED}
)
"""Effects that refuse the request outright.

``DEFERRED`` is deliberately not here: it is not a refusal, it is the
absence of an answer, and a caller has to be able to tell those apart.
"""

PERMITTING_EFFECTS: frozenset[PolicyEffect] = frozenset(
    {PolicyEffect.ALLOW, PolicyEffect.CONDITIONAL_ALLOW}
)
"""Effects under which the caller may proceed immediately.

Narrow on purpose. ``REQUIRE_APPROVAL``, ``REQUIRE_MFA``, and
``ESCALATE`` are *not* permits -- the operation may proceed only once
the named obligation is satisfied, and treating them as allows is the
way an approval gate quietly stops existing.
"""


class RuleOperator(StrEnum):
    """How one condition compares a value (docs/050 "POLICY RULE ENGINE")."""

    EQUALS = "equals"
    NOT_EQUALS = "not_equals"
    IN = "in"
    NOT_IN = "not_in"
    CONTAINS = "contains"
    NOT_CONTAINS = "not_contains"
    STARTS_WITH = "starts_with"
    ENDS_WITH = "ends_with"
    MATCHES = "matches"
    NOT_MATCHES = "not_matches"
    GREATER_THAN = "greater_than"
    GREATER_OR_EQUAL = "greater_or_equal"
    LESS_THAN = "less_than"
    LESS_OR_EQUAL = "less_or_equal"
    BETWEEN = "between"
    EXISTS = "exists"
    NOT_EXISTS = "not_exists"
    IS_EMPTY = "is_empty"
    IS_NOT_EMPTY = "is_not_empty"
    SUBSET_OF = "subset_of"
    SUPERSET_OF = "superset_of"
    INTERSECTS = "intersects"
    TIME_BETWEEN = "time_between"
    DAY_OF_WEEK_IN = "day_of_week_in"
    CIDR_CONTAINS = "cidr_contains"


class LogicalOperator(StrEnum):
    """How a rule combines its conditions."""

    ALL = "all"
    ANY = "any"
    NONE = "none"


class AttributeSource(StrEnum):
    """Where an attribute is read from (docs/050 "ABAC" and "CONTEXT")."""

    SUBJECT = "subject"
    RESOURCE = "resource"
    ACTION = "action"
    CONTEXT = "context"
    ENVIRONMENT = "environment"
    ORGANIZATION = "organization"
    PROJECT = "project"
    CUSTOM = "custom"


class PolicyStatus(StrEnum):
    """Where a policy is in its lifecycle (docs/050 "POLICY VERSIONING")."""

    DRAFT = "draft"
    REVIEW = "review"
    APPROVED = "approved"
    PUBLISHED = "published"
    ARCHIVED = "archived"


EVALUABLE_STATUSES: frozenset[PolicyStatus] = frozenset({PolicyStatus.PUBLISHED})
"""The only status a policy may be evaluated in.

A draft must never influence a live decision. That is the entire point
of having a lifecycle, and it is why evaluation filters on status rather
than trusting an ``is_active`` flag somebody could set by accident.
"""


class ApprovalType(StrEnum):
    """How an approval requirement is satisfied (docs/050 "APPROVAL POLICIES")."""

    SINGLE = "single"
    MULTI_LEVEL = "multi_level"
    ROLE = "role"
    RISK_BASED = "risk_based"
    EMERGENCY = "emergency"
    AUTOMATIC = "automatic"


class ApprovalStatus(StrEnum):
    """Where one approval request stands."""

    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    EXPIRED = "expired"
    CANCELLED = "cancelled"


class QuotaScope(StrEnum):
    """What a quota is counted against (docs/050 "QUOTA POLICIES")."""

    ORGANIZATION = "organization"
    PROJECT = "project"
    USER = "user"
    API_USAGE = "api_usage"
    AUTOMATION_EXECUTIONS = "automation_executions"
    WORKFLOW_EXECUTIONS = "workflow_executions"
    STORAGE = "storage"
    REPORTS = "reports"
    DASHBOARDS = "dashboards"
    CUSTOM_RESOURCE = "custom_resource"


class QuotaPeriod(StrEnum):
    """The window a quota resets on."""

    HOURLY = "hourly"
    DAILY = "daily"
    WEEKLY = "weekly"
    MONTHLY = "monthly"
    TOTAL = "total"


class ComplianceStandard(StrEnum):
    """What a compliance rule checks (docs/050 "COMPLIANCE POLICIES")."""

    SECURITY = "security"
    CONFIGURATION = "configuration"
    NAMING = "naming"
    RETENTION = "retention"
    PASSWORD = "password"
    INFRASTRUCTURE = "infrastructure"
    CUSTOM = "custom"


class ViolationStatus(StrEnum):
    """Where a recorded violation stands."""

    OPEN = "open"
    ACKNOWLEDGED = "acknowledged"
    RESOLVED = "resolved"
    WAIVED = "waived"


class SimulationKind(StrEnum):
    """What a simulation is asking (docs/050 "POLICY SIMULATION")."""

    WHAT_IF = "what_if"
    PREVIEW = "preview"
    IMPACT_ANALYSIS = "impact_analysis"
    CONFLICT_DETECTION = "conflict_detection"
    COMPARISON = "comparison"


class ReportKind(StrEnum):
    """What a generated report covers (docs/050 "REPORTING")."""

    POLICY = "policy"
    VIOLATION = "violation"
    COMPLIANCE = "compliance"
    DECISION = "decision"
    APPROVAL = "approval"
    EXECUTIVE = "executive"


class JobStatus(StrEnum):
    """Where one background job stands."""

    PENDING = "pending"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"


class AuditAction(StrEnum):
    """What an audited action did (docs/050 "AUDIT")."""

    POLICY_CHANGED = "policy.changed"
    RULE_CHANGED = "rule.changed"
    DECISION_MADE = "decision.made"
    VIOLATION_RECORDED = "violation.recorded"
    APPROVAL_CHANGED = "approval.changed"
    SIMULATION_RUN = "simulation.run"
    ADMINISTRATIVE = "administrative"


class AuditOutcome(StrEnum):
    """Whether an audited action succeeded."""

    SUCCESS = "success"
    FAILURE = "failure"
    DENIED = "denied"


__all__ = [
    "DENYING_EFFECTS",
    "EFFECT_PRECEDENCE",
    "EVALUABLE_STATUSES",
    "PERMITTING_EFFECTS",
    "ActionType",
    "ApprovalStatus",
    "ApprovalType",
    "AttributeSource",
    "AuditAction",
    "AuditOutcome",
    "ComplianceStandard",
    "JobStatus",
    "LogicalOperator",
    "PolicyCategory",
    "PolicyEffect",
    "PolicyStatus",
    "PolicyType",
    "QuotaPeriod",
    "QuotaScope",
    "ReportKind",
    "ResourceType",
    "RuleOperator",
    "SimulationKind",
    "SubjectType",
    "ViolationStatus",
]
