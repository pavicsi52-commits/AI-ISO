"""Enumerations for the Alerting Service, per docs/045
"Enterprise Alerting Service".

**Reuse note**: alert severity is NOT reinvented here.
``shared_core.enums.severity.Severity`` (``CRITICAL``/``HIGH``/
``MEDIUM``/``LOW``/``INFO``) is imported and used directly for
``AlertInstance.severity``/``AlertRoute.severity_filter`` -- its own
module docstring explicitly names "validation, alerting, and logging"
as intended consumers, and docs/045's own "ALERT SEVERITY" list
(Critical, High, Medium, Low, Informational) matches it exactly. This
is the correct reuse call this platform's own shared enum was built
for, even though an earlier service
(``services/validation-service``'s own ``ValidationSeverity``) missed
it and defined a parallel duplicate instead -- not revisited here since
that is a different, already-shipped service outside this prompt's own
scope.
"""

from __future__ import annotations

from enum import StrEnum


class AlertStatus(StrEnum):
    """Per docs/045 "ALERT STATUS"."""

    NEW = "new"
    OPEN = "open"
    ACKNOWLEDGED = "acknowledged"
    INVESTIGATING = "investigating"
    SUPPRESSED = "suppressed"
    ESCALATED = "escalated"
    RESOLVED = "resolved"
    CLOSED = "closed"
    EXPIRED = "expired"


class AlertSource(StrEnum):
    """Per docs/045 "ALERT SOURCES". ``FUTURE_AI`` is reserved -- no AI
    service exists yet to integrate with (docs/045's own literal
    "Future AI Events" line), backed by no client of this service's own.
    """

    MONITORING = "monitoring"
    VALIDATION = "validation"
    AUTOMATION = "automation"
    WORKFLOW_RUNTIME = "workflow_runtime"
    CONFIGURATION_MANAGEMENT = "configuration_management"
    DISCOVERY = "discovery"
    INVENTORY = "inventory"
    SYSTEM_EVENTS = "system_events"
    APPLICATION_EVENTS = "application_events"
    CUSTOM_EVENTS = "custom_events"
    FUTURE_AI = "future_ai"


class AlertRuleType(StrEnum):
    """Per docs/045 "RULE ENGINE" "Support"."""

    METRIC_THRESHOLD = "metric_threshold"
    VALIDATION_RULE = "validation_rule"
    COMPOSITE = "composite"
    DEPENDENCY = "dependency"
    TIME_WINDOW = "time_window"
    RATE_OF_CHANGE = "rate_of_change"
    PATTERN_MATCHING = "pattern_matching"
    BOOLEAN_LOGIC = "boolean_logic"
    EVENT_AGGREGATION = "event_aggregation"
    CUSTOM_EXPRESSION = "custom_expression"


class BooleanOperator(StrEnum):
    """How an :class:`~app.models.alert_rule.AlertRule`'s own
    :class:`~app.models.alert_condition.AlertCondition` rows combine --
    not its own named list in docs/045, but required by "Boolean Logic"
    and "Composite Rules", added directly the same "required concept,
    no literal list" precedent every prior AI-IOS service has
    established at least once.
    """

    AND = "and"
    OR = "or"


class CorrelationType(StrEnum):
    """Per docs/045 "CORRELATION" "Support"."""

    TOPOLOGY = "topology"
    TIME = "time"
    DEPENDENCY = "dependency"
    APPLICATION = "application"
    INFRASTRUCTURE = "infrastructure"
    SERVICE = "service"
    WORKFLOW = "workflow"
    CUSTOM = "custom"


class DeduplicationStrategy(StrEnum):
    """Per docs/045 "DEDUPLICATION" "Support" -- the mechanism by which
    two alerts were determined to be duplicates ("Duplicate Detection"/
    "Event Consolidation" are the outcome/process, not a strategy value
    of their own, so only the four genuinely distinct mechanisms are
    represented as enum members).
    """

    FINGERPRINT = "fingerprint"
    HASH_MATCH = "hash_match"
    TIME_WINDOW = "time_window"
    RULE_BASED = "rule_based"


class SuppressionType(StrEnum):
    """Per docs/045 "SUPPRESSION" "Support"."""

    MAINTENANCE_WINDOW = "maintenance_window"
    SCHEDULED = "scheduled"
    DEPENDENCY = "dependency"
    PARENT_CHILD = "parent_child"
    TEMPORARY = "temporary"
    RULE_BASED = "rule_based"
    MANUAL = "manual"


class AlertRouteChannel(StrEnum):
    """Per docs/045 "ROUTING" "Support". ``CUSTOM`` backs "Custom Connectors"."""

    EMAIL = "email"
    SMS = "sms"
    SLACK = "slack"
    TEAMS = "teams"
    DISCORD = "discord"
    WEBHOOK = "webhook"
    PAGERDUTY = "pagerduty"
    SERVICENOW = "servicenow"
    OPSGENIE = "opsgenie"
    CUSTOM = "custom"


class RouteTargetType(StrEnum):
    """Per docs/045 "ROUTING" "Support": Role-based Routing,
    Organization Routing, Project Routing -- who/what a route actually
    delivers to.
    """

    USER = "user"
    ROLE = "role"
    ORGANIZATION = "organization"
    PROJECT = "project"


class EscalationTargetType(StrEnum):
    """Per docs/045 "ESCALATION" "Support": Manager Escalation, On-call
    Escalation, Workflow Escalation, plus the two base target kinds
    every escalation level ultimately resolves to.
    """

    USER = "user"
    ROLE = "role"
    MANAGER = "manager"
    ONCALL_SCHEDULE = "oncall_schedule"
    WORKFLOW = "workflow"


class AcknowledgementType(StrEnum):
    """Per docs/045 "ACKNOWLEDGEMENT" "Support": Manual Acknowledgement,
    Automatic Acknowledgement.
    """

    MANUAL = "manual"
    AUTOMATIC = "automatic"


class MaintenanceWindowType(StrEnum):
    """Per docs/045 "MAINTENANCE WINDOWS" "Support"."""

    SCHEDULED = "scheduled"
    RECURRING = "recurring"
    EMERGENCY = "emergency"


class MaintenanceWindowScope(StrEnum):
    """Per docs/045 "MAINTENANCE WINDOWS" "Support": Asset Scope, Group
    Scope, Organization Scope, Project Scope.
    """

    ASSET = "asset"
    GROUP = "group"
    ORGANIZATION = "organization"
    PROJECT = "project"


class OnCallRotationType(StrEnum):
    """Not its own named list in docs/045's own "ON-CALL MANAGEMENT"
    section ("Rotations" names the capability, not its own concrete
    values), added directly the same "required concept, no literal
    list" precedent every prior AI-IOS service has established at least
    once, matching common on-call rotation cadences.
    """

    DAILY = "daily"
    WEEKLY = "weekly"
    BIWEEKLY = "biweekly"
    CUSTOM = "custom"


class NotificationDeliveryStatus(StrEnum):
    """Not its own named list in docs/045, but required by
    "NOTIFICATIONS"' own "Retry"/"Delivery Tracking" support lines,
    added directly the same "required concept, no literal list"
    precedent every prior AI-IOS service has established at least once.
    """

    PENDING = "pending"
    SENT = "sent"
    FAILED = "failed"
    RETRYING = "retrying"


class AlertReportType(StrEnum):
    """Per docs/045 "REPORTING" "Generate"."""

    ALERT = "alert"
    EXECUTIVE = "executive"
    OPERATIONAL = "operational"
    SLA = "sla"
    ESCALATION = "escalation"
    TREND = "trend"
    NOISE_ANALYSIS = "noise_analysis"


class AuditOutcome(StrEnum):
    """Matches every prior AI-IOS service's own identical
    ``AuditOutcome`` shape.
    """

    SUCCESS = "success"
    FAILURE = "failure"


__all__ = [
    "AcknowledgementType",
    "AlertReportType",
    "AlertRouteChannel",
    "AlertRuleType",
    "AlertSource",
    "AlertStatus",
    "AuditOutcome",
    "BooleanOperator",
    "CorrelationType",
    "DeduplicationStrategy",
    "EscalationTargetType",
    "MaintenanceWindowScope",
    "MaintenanceWindowType",
    "NotificationDeliveryStatus",
    "OnCallRotationType",
    "RouteTargetType",
    "SuppressionType",
]
