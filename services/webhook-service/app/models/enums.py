"""The platform's fixed webhook vocabulary (docs/057).

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


class WebhookKind(StrEnum):
    """The seven webhook types docs/057 names."""

    INCOMING = "incoming"
    OUTGOING = "outgoing"
    INTERNAL_EVENT = "internal_event"
    PARTNER = "partner"
    ORGANIZATION = "organization"
    PROJECT = "project"
    CUSTOM = "custom"


class EventSource(StrEnum):
    """Where a webhook-worthy event originated."""

    AUTOMATION = "automation"
    WORKFLOW_RUNTIME = "workflow_runtime"
    VALIDATION = "validation"
    MONITORING = "monitoring"
    ALERTING = "alerting"
    DASHBOARD = "dashboard"
    KNOWLEDGE_GRAPH = "knowledge_graph"
    COMPLIANCE = "compliance"
    POLICY_ENGINE = "policy_engine"
    SCHEDULER = "scheduler"
    INCIDENT_MANAGEMENT = "incident_management"
    CHANGE_MANAGEMENT = "change_management"
    NOTIFICATION_CENTER = "notification_center"
    AI_ASSISTANT = "ai_assistant"
    ADMINISTRATION = "administration"
    CUSTOM = "custom"


class SubscriptionScope(StrEnum):
    """The nine subscription shapes docs/057 names."""

    ORGANIZATION = "organization"
    PROJECT = "project"
    ROLE = "role"
    USER = "user"
    TOPIC = "topic"
    EVENT = "event"
    RESOURCE = "resource"
    WILDCARD = "wildcard"
    CONDITIONAL = "conditional"


class FilterMatchMode(StrEnum):
    """Whether a filter's own rules must all match, or any one of them."""

    ALL = "all"
    ANY = "any"


class TransformationKind(StrEnum):
    """The nine payload-transformation kinds docs/057 names."""

    JSON_MAPPING = "json_mapping"
    HEADER_MAPPING = "header_mapping"
    FIELD_RENAME = "field_rename"
    FIELD_REMOVAL = "field_removal"
    FIELD_ENRICHMENT = "field_enrichment"
    TEMPLATE_RENDERING = "template_rendering"
    METADATA_INJECTION = "metadata_injection"
    VERSION_CONVERSION = "version_conversion"
    CUSTOM = "custom"


class WebhookAuthMethod(StrEnum):
    """How an outgoing delivery proves its own identity to the receiver."""

    NONE = "none"
    HMAC_SHA256 = "hmac_sha256"
    HMAC_SHA512 = "hmac_sha512"
    API_KEY = "api_key"
    JWT = "jwt"
    OAUTH2 = "oauth2"
    MUTUAL_TLS = "mutual_tls"


class SignatureAlgorithm(StrEnum):
    """The two HMAC algorithms docs/057 names for signature generation/verification."""

    HMAC_SHA256 = "hmac_sha256"
    HMAC_SHA512 = "hmac_sha512"


class SecretStatus(StrEnum):
    """A signing secret's own lifecycle, for rotation with overlap."""

    ACTIVE = "active"
    ROTATING = "rotating"
    EXPIRED = "expired"
    REVOKED = "revoked"


class IdempotencyStatus(StrEnum):
    """Whether a caller-supplied idempotency key's own result is settled yet."""

    PENDING = "pending"
    COMPLETED = "completed"
    EXPIRED = "expired"


class DeliveryStatus(StrEnum):
    """Every state docs/057's own "DELIVERY TRACKING" section names."""

    QUEUED = "queued"
    PROCESSING = "processing"
    DELIVERED = "delivered"
    FAILED = "failed"
    RETRIED = "retried"
    EXPIRED = "expired"
    CANCELLED = "cancelled"
    ACKNOWLEDGED = "acknowledged"


TERMINAL_DELIVERY_STATUSES = frozenset(
    {
        DeliveryStatus.DELIVERED,
        DeliveryStatus.EXPIRED,
        DeliveryStatus.CANCELLED,
        DeliveryStatus.ACKNOWLEDGED,
    }
)
"""Statuses a delivery never leaves once reached -- ``FAILED`` is
deliberately excluded, since a failed delivery still retries until it
either succeeds or exhausts its own retry policy into ``EXPIRED``."""


class DeliveryMode(StrEnum):
    """The eight delivery strategies docs/057's own "DELIVERY MANAGEMENT" section names."""

    IMMEDIATE = "immediate"
    QUEUED = "queued"
    PRIORITY = "priority"
    BULK = "bulk"
    SCHEDULED = "scheduled"
    DELAYED = "delayed"
    PARALLEL = "parallel"
    ORDERED = "ordered"


class RetryBackoffStrategy(StrEnum):
    """The two backoff shapes docs/057's own "RETRY MANAGEMENT" section names."""

    EXPONENTIAL = "exponential"
    LINEAR = "linear"


class EndpointStatus(StrEnum):
    """A registered outgoing-delivery target's own lifecycle."""

    ACTIVE = "active"
    DISABLED = "disabled"
    UNHEALTHY = "unhealthy"


class ReplayScope(StrEnum):
    """The four replay-selection shapes docs/057's own "REPLAY" section names."""

    BY_EVENT = "by_event"
    BY_ENDPOINT = "by_endpoint"
    BY_DATE_RANGE = "by_date_range"
    BY_SUBSCRIPTION = "by_subscription"


class ReplayStatus(StrEnum):
    """A replay job's own lifecycle."""

    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class ReportKind(StrEnum):
    """The seven report kinds docs/057's own "REPORTING" section names."""

    DELIVERY = "delivery"
    FAILURE = "failure"
    RETRY = "retry"
    ENDPOINT = "endpoint"
    REPLAY = "replay"
    SECURITY = "security"
    AUDIT = "audit"


class ReportFormat(StrEnum):
    """How a report is rendered."""

    JSON = "json"
    CSV = "csv"
    MARKDOWN = "markdown"


class ReportStatus(StrEnum):
    """A generated report's own build lifecycle."""

    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class AuditAction(StrEnum):
    """What an audit row records (docs/057 "AUDIT")."""

    ENDPOINT_REGISTERED = "endpoint_registered"
    ENDPOINT_UPDATED = "endpoint_updated"
    ENDPOINT_DELETED = "endpoint_deleted"
    SUBSCRIPTION_CREATED = "subscription_created"
    SUBSCRIPTION_UPDATED = "subscription_updated"
    SUBSCRIPTION_DELETED = "subscription_deleted"
    SECRET_ROTATED = "secret_rotated"
    DELIVERY_RETRIED = "delivery_retried"
    REPLAY_STARTED = "replay_started"
    ADMINISTRATIVE = "administrative"


class WebhookStreamEventKind(StrEnum):
    """Frames a WebSocket subscriber to this service's live stream can receive.

    Not database-persisted -- a presentation-layer vocabulary, kept here
    alongside the rest of this service's fixed vocabulary, mirroring
    api-gateway-service's own ``GatewayStreamEventKind`` placement.
    """

    DELIVERY_UPDATED = "delivery_updated"
    RETRY_SCHEDULED = "retry_scheduled"
    DEAD_LETTERED = "dead_lettered"
    HEARTBEAT = "heartbeat"


# ---- normalisers ---------------------------------------------------------


def webhook_kind_of(value: str | WebhookKind) -> WebhookKind:
    """Coerce a stored value to :class:`WebhookKind`."""
    return value if isinstance(value, WebhookKind) else WebhookKind(value)


def event_source_of(value: str | EventSource) -> EventSource:
    """Coerce a stored value to :class:`EventSource`."""
    return value if isinstance(value, EventSource) else EventSource(value)


def subscription_scope_of(value: str | SubscriptionScope) -> SubscriptionScope:
    """Coerce a stored value to :class:`SubscriptionScope`."""
    return value if isinstance(value, SubscriptionScope) else SubscriptionScope(value)


def filter_match_mode_of(value: str | FilterMatchMode) -> FilterMatchMode:
    """Coerce a stored value to :class:`FilterMatchMode`."""
    return value if isinstance(value, FilterMatchMode) else FilterMatchMode(value)


def transformation_kind_of(value: str | TransformationKind) -> TransformationKind:
    """Coerce a stored value to :class:`TransformationKind`."""
    return value if isinstance(value, TransformationKind) else TransformationKind(value)


def webhook_auth_method_of(value: str | WebhookAuthMethod) -> WebhookAuthMethod:
    """Coerce a stored value to :class:`WebhookAuthMethod`."""
    return value if isinstance(value, WebhookAuthMethod) else WebhookAuthMethod(value)


def signature_algorithm_of(value: str | SignatureAlgorithm) -> SignatureAlgorithm:
    """Coerce a stored value to :class:`SignatureAlgorithm`."""
    return value if isinstance(value, SignatureAlgorithm) else SignatureAlgorithm(value)


def secret_status_of(value: str | SecretStatus) -> SecretStatus:
    """Coerce a stored value to :class:`SecretStatus`."""
    return value if isinstance(value, SecretStatus) else SecretStatus(value)


def idempotency_status_of(value: str | IdempotencyStatus) -> IdempotencyStatus:
    """Coerce a stored value to :class:`IdempotencyStatus`."""
    return value if isinstance(value, IdempotencyStatus) else IdempotencyStatus(value)


def delivery_status_of(value: str | DeliveryStatus) -> DeliveryStatus:
    """Coerce a stored value to :class:`DeliveryStatus`."""
    return value if isinstance(value, DeliveryStatus) else DeliveryStatus(value)


def delivery_mode_of(value: str | DeliveryMode) -> DeliveryMode:
    """Coerce a stored value to :class:`DeliveryMode`."""
    return value if isinstance(value, DeliveryMode) else DeliveryMode(value)


def retry_backoff_strategy_of(value: str | RetryBackoffStrategy) -> RetryBackoffStrategy:
    """Coerce a stored value to :class:`RetryBackoffStrategy`."""
    return value if isinstance(value, RetryBackoffStrategy) else RetryBackoffStrategy(value)


def endpoint_status_of(value: str | EndpointStatus) -> EndpointStatus:
    """Coerce a stored value to :class:`EndpointStatus`."""
    return value if isinstance(value, EndpointStatus) else EndpointStatus(value)


def replay_scope_of(value: str | ReplayScope) -> ReplayScope:
    """Coerce a stored value to :class:`ReplayScope`."""
    return value if isinstance(value, ReplayScope) else ReplayScope(value)


def replay_status_of(value: str | ReplayStatus) -> ReplayStatus:
    """Coerce a stored value to :class:`ReplayStatus`."""
    return value if isinstance(value, ReplayStatus) else ReplayStatus(value)


def report_kind_of(value: str | ReportKind) -> ReportKind:
    """Coerce a stored value to :class:`ReportKind`."""
    return value if isinstance(value, ReportKind) else ReportKind(value)


def report_format_of(value: str | ReportFormat) -> ReportFormat:
    """Coerce a stored value to :class:`ReportFormat`."""
    return value if isinstance(value, ReportFormat) else ReportFormat(value)


def report_status_of(value: str | ReportStatus) -> ReportStatus:
    """Coerce a stored value to :class:`ReportStatus`."""
    return value if isinstance(value, ReportStatus) else ReportStatus(value)


def audit_action_of(value: str | AuditAction) -> AuditAction:
    """Coerce a stored value to :class:`AuditAction`."""
    return value if isinstance(value, AuditAction) else AuditAction(value)


__all__ = [
    "TERMINAL_DELIVERY_STATUSES",
    "AuditAction",
    "DeliveryMode",
    "DeliveryStatus",
    "EndpointStatus",
    "EventSource",
    "FilterMatchMode",
    "IdempotencyStatus",
    "ReplayScope",
    "ReplayStatus",
    "ReportFormat",
    "ReportKind",
    "ReportStatus",
    "RetryBackoffStrategy",
    "SecretStatus",
    "SignatureAlgorithm",
    "SubscriptionScope",
    "TransformationKind",
    "WebhookAuthMethod",
    "WebhookKind",
    "WebhookStreamEventKind",
    "audit_action_of",
    "delivery_mode_of",
    "delivery_status_of",
    "endpoint_status_of",
    "event_source_of",
    "filter_match_mode_of",
    "idempotency_status_of",
    "replay_scope_of",
    "replay_status_of",
    "report_format_of",
    "report_kind_of",
    "report_status_of",
    "retry_backoff_strategy_of",
    "secret_status_of",
    "signature_algorithm_of",
    "subscription_scope_of",
    "transformation_kind_of",
    "webhook_auth_method_of",
    "webhook_kind_of",
]
