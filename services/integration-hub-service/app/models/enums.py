"""Every enum this service's own models and pure engines use.

Every ``Mapped[SomeEnum]`` column here is backed by ``String`` at the
database level (SQLAlchemy's own ``StrEnum``-as-``str`` convention used
consistently across this platform) -- callers pass the column itself to
a normaliser, never the record, per this platform's own established
"enum-as-str" rule (round-tripping a row loses the Python enum type,
leaving a plain ``str`` that happens to share the same value).

Two enums are reused directly from ``shared_core`` rather than
redeclared here: ``shared_core.enums.health_status.HealthStatus`` (six
values -- healthy/degraded/warning/unhealthy/maintenance/unknown, this
platform's own established health vocabulary) and
``shared_core.connectors.credentials.CredentialType`` (eight values --
docs/027's own "AUTHENTICATION" credential-material taxonomy). Both are
re-exported from :mod:`app.models` for a single import surface.
"""

from __future__ import annotations

from enum import StrEnum


class ConnectorCategory(StrEnum):
    """The fifteen categories docs/058's own "CONNECTOR CATEGORIES" names."""

    CLOUD = "cloud"
    VIRTUALIZATION = "virtualization"
    CONTAINER_PLATFORMS = "container_platforms"
    MONITORING = "monitoring"
    ITSM = "itsm"
    DEVOPS = "devops"
    IDENTITY = "identity"
    NETWORKING = "networking"
    STORAGE = "storage"
    DATABASES = "databases"
    INDUSTRIAL_PROTOCOLS = "industrial_protocols"
    MESSAGING = "messaging"
    SECURITY = "security"
    BUSINESS_APPLICATIONS = "business_applications"
    CUSTOM = "custom"


class ConnectorLifecycleStatus(StrEnum):
    """Docs/058's own "CONNECTOR LIFECYCLE" progression.

    Not strictly linear -- ``ENABLED``/``DISABLED`` toggle back and
    forth, ``UPGRADE``/``ROLLBACK`` are transitions between two
    ``connector_versions`` rows rather than states of their own (see
    ``ConnectorService.upgrade``/``.rollback``), and ``DEPRECATED``/
    ``REMOVED`` are terminal.
    """

    REGISTERED = "registered"
    INSTALLED = "installed"
    CONFIGURED = "configured"
    VALIDATED = "validated"
    ENABLED = "enabled"
    DISABLED = "disabled"
    DEPRECATED = "deprecated"
    REMOVED = "removed"


class ConnectorAuthMethod(StrEnum):
    """Docs/058's own "AUTHENTICATION" section -- the protocol a connector speaks.

    Distinct from ``shared_core.connectors.credentials.CredentialType``
    (what kind of secret *material* is stored) the same way
    webhook-service's own ``WebhookAuthMethod`` is distinct from its
    ``SignatureAlgorithm`` -- one connector's auth method (say,
    ``OAUTH2``) determines which ``CredentialType`` its own
    ``connector_credentials`` row must hold (``CredentialType.OAUTH2``).
    """

    OAUTH2 = "oauth2"
    OIDC = "oidc"
    API_KEY = "api_key"
    JWT = "jwt"
    BASIC = "basic"
    BEARER_TOKEN = "bearer_token"
    MUTUAL_TLS = "mutual_tls"
    CERTIFICATE = "certificate"
    USERNAME_PASSWORD = "username_password"
    CUSTOM = "custom"


class CredentialStatus(StrEnum):
    """A ``connector_credentials`` row's own lifecycle."""

    PENDING_VALIDATION = "pending_validation"
    ACTIVE = "active"
    EXPIRED = "expired"
    REVOKED = "revoked"
    ROTATING = "rotating"


class ConnectionStatus(StrEnum):
    """One ``connector_connections`` test/session attempt's outcome."""

    TESTING = "testing"
    SUCCESS = "success"
    FAILED = "failed"
    TIMEOUT = "timeout"


class SyncMode(StrEnum):
    """Docs/058's own "DATA SYNCHRONIZATION" transfer shape."""

    ONE_WAY = "one_way"
    TWO_WAY = "two_way"
    INCREMENTAL = "incremental"
    FULL = "full"


class SyncTrigger(StrEnum):
    """What started one ``connector_sync_jobs`` row."""

    SCHEDULED = "scheduled"
    MANUAL = "manual"
    EVENT_DRIVEN = "event_driven"


class SyncStatus(StrEnum):
    """One sync job's own run state."""

    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    PARTIALLY_COMPLETED = "partially_completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class ConflictResolution(StrEnum):
    """How a two-way sync resolves a field that changed on both sides."""

    SOURCE_WINS = "source_wins"
    TARGET_WINS = "target_wins"
    MANUAL = "manual"
    MERGE = "merge"
    SKIP = "skip"


class DataFormat(StrEnum):
    """The four formats docs/058's own "DATA TRANSFORMATION" section names.

    A genuine gap, not reused from
    ``shared_core.requests.import_export.DataFormat`` -- that enum
    covers only JSON/CSV/YAML for generic bulk import/export request
    schemas and has no XML member, which this service's own
    transformation engine needs.
    """

    JSON = "json"
    XML = "xml"
    CSV = "csv"
    YAML = "yaml"


class TransformationKind(StrEnum):
    """One transformation rule's own operation."""

    FIELD_MAPPING = "field_mapping"
    SCHEMA_VALIDATION = "schema_validation"
    ENRICHMENT = "enrichment"
    FILTERING = "filtering"
    AGGREGATION = "aggregation"
    NORMALIZATION = "normalization"
    FORMAT_CONVERSION = "format_conversion"


class FlowStatus(StrEnum):
    """A flow definition's own own lifecycle."""

    DRAFT = "draft"
    ACTIVE = "active"
    DISABLED = "disabled"
    ARCHIVED = "archived"


class FlowTrigger(StrEnum):
    """What starts one flow run."""

    MANUAL = "manual"
    SCHEDULED = "scheduled"
    EVENT = "event"


class FlowRunStatus(StrEnum):
    """A flow's own most recent execution outcome."""

    NEVER_RUN = "never_run"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    AWAITING_APPROVAL = "awaiting_approval"
    CANCELLED = "cancelled"


class FlowStepKind(StrEnum):
    """One node in a flow definition's own step graph.

    Used inside ``connector_flows.definition`` (JSON), not as its own
    database column -- docs/058's own "DATABASE TABLES" section lists
    no separate flow-step table, so a flow's steps live as structured
    JSON on the one row that owns them, the same "no table beyond the
    literal list" discipline every prior AI-IOS service applies.
    """

    ACTION = "action"
    CONDITION = "condition"
    BRANCH = "branch"
    LOOP = "loop"
    PARALLEL = "parallel"
    APPROVAL = "approval"
    COMPENSATION = "compensation"


class EventSource(StrEnum):
    """Docs/058's own "EVENT ROUTING" section's event origins."""

    INTERNAL = "internal"
    WEBHOOK = "webhook"
    MESSAGE_QUEUE = "message_queue"
    REST = "rest"
    GRAPHQL = "graphql"
    STREAMING = "streaming"
    BROADCAST = "broadcast"


class EventRoutingStatus(StrEnum):
    """One ``connector_events`` row's own routing outcome."""

    PENDING = "pending"
    ROUTED = "routed"
    FILTERED = "filtered"
    FAILED = "failed"


class MarketplaceStatus(StrEnum):
    """One ``connector_marketplace`` catalog entry's own publication state."""

    BETA = "beta"
    PUBLISHED = "published"
    DEPRECATED = "deprecated"
    ARCHIVED = "archived"


class ReportKind(StrEnum):
    """The seven report kinds docs/058's own "REPORTING" section names."""

    CONNECTOR = "connector"
    SYNCHRONIZATION = "synchronization"
    HEALTH = "health"
    CREDENTIAL = "credential"
    MARKETPLACE = "marketplace"
    PERFORMANCE = "performance"
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
    """What an audit row records (docs/058 "AUDIT")."""

    CONNECTOR_REGISTERED = "connector_registered"
    CONNECTOR_CONFIGURED = "connector_configured"
    CONNECTOR_ENABLED = "connector_enabled"
    CONNECTOR_DISABLED = "connector_disabled"
    CONNECTOR_UPGRADED = "connector_upgraded"
    CONNECTOR_ROLLED_BACK = "connector_rolled_back"
    CONNECTOR_REMOVED = "connector_removed"
    CREDENTIAL_ASSIGNED = "credential_assigned"
    CREDENTIAL_ROTATED = "credential_rotated"
    SYNC_TRIGGERED = "sync_triggered"
    FLOW_EXECUTED = "flow_executed"
    MARKETPLACE_PUBLISHED = "marketplace_published"
    ADMINISTRATIVE = "administrative"


__all__ = [
    "AuditAction",
    "ConflictResolution",
    "ConnectionStatus",
    "ConnectorAuthMethod",
    "ConnectorCategory",
    "ConnectorLifecycleStatus",
    "CredentialStatus",
    "DataFormat",
    "EventRoutingStatus",
    "EventSource",
    "FlowRunStatus",
    "FlowStatus",
    "FlowStepKind",
    "FlowTrigger",
    "MarketplaceStatus",
    "ReportFormat",
    "ReportKind",
    "ReportStatus",
    "SyncMode",
    "SyncStatus",
    "SyncTrigger",
    "TransformationKind",
]
