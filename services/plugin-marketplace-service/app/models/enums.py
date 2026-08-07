"""Every enum this service's own models and pure engines use.

Every ``Mapped[SomeEnum]`` column here is backed by ``String`` at the
database level -- callers pass the column itself to a normaliser, never
the record, per this platform's own established "enum-as-str" rule.

``HealthStatus`` is reused directly from
``shared_core.enums.health_status`` rather than redeclared here -- this
platform's own established health vocabulary, re-exported from
:mod:`app.models` for a single import surface.
"""

from __future__ import annotations

from enum import StrEnum


class PluginCategory(StrEnum):
    """The eighteen categories docs/059's own "PLUGIN CATEGORIES" names."""

    AUTOMATION = "automation"
    WORKFLOW = "workflow"
    VALIDATION = "validation"
    MONITORING = "monitoring"
    DISCOVERY = "discovery"
    INVENTORY = "inventory"
    DASHBOARD = "dashboard"
    VISUALIZATION = "visualization"
    AI = "ai"
    REPORTING = "reporting"
    SECURITY = "security"
    COMPLIANCE = "compliance"
    INTEGRATION = "integration"
    CLOUD = "cloud"
    INDUSTRIAL = "industrial"
    DEVELOPER_TOOLS = "developer_tools"
    UTILITIES = "utilities"
    CUSTOM = "custom"


class PluginType(StrEnum):
    """The fifteen types docs/059's own "PLUGIN TYPES" names.

    Distinct from ``shared_core.plugins.metadata.PluginType`` (Prompt
    029's own in-process runtime-loader vocabulary, 16 values, none of
    which match this list) -- this service's own catalog needs docs/059's
    literal taxonomy, not the framework's.
    """

    CORE_EXTENSION = "core_extension"
    CONNECTOR = "connector"
    WIDGET = "widget"
    DASHBOARD = "dashboard"
    WORKFLOW_STEP = "workflow_step"
    AUTOMATION_ACTION = "automation_action"
    VALIDATION_RULE = "validation_rule"
    AI_TOOL = "ai_tool"
    CLI_EXTENSION = "cli_extension"
    FRONTEND_MODULE = "frontend_module"
    BACKEND_MODULE = "backend_module"
    NOTIFICATION_CHANNEL = "notification_channel"
    STORAGE_PROVIDER = "storage_provider"
    AUTHENTICATION_PROVIDER = "authentication_provider"
    CUSTOM_PLUGIN = "custom_plugin"


class PluginLifecycleStatus(StrEnum):
    """One plugin *definition*'s own progression through docs/059's
    "PLUGIN LIFECYCLE" -- registration, validation, publishing, approval.

    Distinct from ``PluginInstallationStatus`` (an organization's own
    installed *instance* of a plugin, which has its own separate
    activate/configure/upgrade/rollback/disable/remove progression).
    """

    REGISTERED = "registered"
    VALIDATED = "validated"
    PUBLISHED = "published"
    PENDING_APPROVAL = "pending_approval"
    APPROVED = "approved"
    REJECTED = "rejected"
    DEPRECATED = "deprecated"
    ARCHIVED = "archived"


class PluginInstallationStatus(StrEnum):
    """One organization's own installed plugin instance's own state."""

    INSTALLING = "installing"
    INSTALLED = "installed"
    ACTIVE = "active"
    CONFIGURED = "configured"
    DISABLED = "disabled"
    UPGRADING = "upgrading"
    ROLLING_BACK = "rolling_back"
    REMOVING = "removing"
    REMOVED = "removed"
    FAILED = "failed"


class PackageFormat(StrEnum):
    """How a plugin's own package artifact is compressed."""

    TAR_GZ = "tar_gz"
    ZIP = "zip"


class ManifestValidationStatus(StrEnum):
    """One manifest's own structural-validation outcome."""

    PENDING = "pending"
    VALID = "valid"
    INVALID = "invalid"


class PluginPermissionCategory(StrEnum):
    """The eleven capability categories docs/059's own "PERMISSION MODEL" names.

    Distinct from ``shared_core.plugins.permissions.PluginPermission``
    (Prompt 029's own nine-value in-process vocabulary, which does not
    cover Inventory/Automation/Secrets/Knowledge-Graph/Monitoring/API) --
    this service's own capability-grant model needs docs/059's literal
    taxonomy.
    """

    INVENTORY = "inventory"
    AUTOMATION = "automation"
    WORKFLOW = "workflow"
    SECRETS = "secrets"
    KNOWLEDGE_GRAPH = "knowledge_graph"
    MONITORING = "monitoring"
    NOTIFICATION = "notification"
    API = "api"
    FILESYSTEM = "filesystem"
    NETWORK = "network"
    CUSTOM = "custom"


class PermissionGrantStatus(StrEnum):
    """One requested capability's own grant state."""

    PENDING = "pending"
    GRANTED = "granted"
    DENIED = "denied"
    REVOKED = "revoked"


class InstallationTrigger(StrEnum):
    """What initiated one installation."""

    ONLINE = "online"
    OFFLINE = "offline"
    BULK = "bulk"
    SCHEDULED = "scheduled"


class UpgradeStrategy(StrEnum):
    """How one upgrade is rolled out."""

    AUTOMATIC = "automatic"
    MANUAL = "manual"
    CANARY = "canary"


class UpgradeStatus(StrEnum):
    """One upgrade's own run state."""

    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"


class RollbackStatus(StrEnum):
    """One rollback's own run state."""

    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"


class ReviewStatus(StrEnum):
    """One review's own moderation state."""

    PENDING = "pending"
    PUBLISHED = "published"
    FLAGGED = "flagged"
    REMOVED = "removed"


class PublisherType(StrEnum):
    """The four publisher kinds docs/059's own "PUBLISHERS" section names."""

    INDIVIDUAL = "individual"
    ORGANIZATION = "organization"
    PARTNER = "partner"
    PRIVATE = "private"


class PublisherVerificationStatus(StrEnum):
    """One publisher's own verification state."""

    UNVERIFIED = "unverified"
    PENDING = "pending"
    VERIFIED = "verified"
    REVOKED = "revoked"


class MarketplaceListingStatus(StrEnum):
    """One marketplace listing's own publication state."""

    DRAFT = "draft"
    PUBLISHED = "published"
    FEATURED = "featured"
    DEPRECATED = "deprecated"
    REMOVED = "removed"


class SignatureAlgorithm(StrEnum):
    """The one signing algorithm this service supports.

    Ed25519 -- the established precedent ``playbook-service``'s own
    content-signing already uses (fast, small signatures, matches the
    tamper-detection/checksum-verification semantics docs/059 asks for)
    -- rather than the RSA-PSS scheme ``shared_core.plugins.manifest
    .sign_manifest`` hardcodes, which stays available separately for
    manifest-level (not package-level) signing if ever wanted.
    """

    ED25519 = "ed25519"


class ReportKind(StrEnum):
    """The seven report kinds docs/059's own "REPORTING" section names."""

    MARKETPLACE = "marketplace"
    PLUGIN_HEALTH = "plugin_health"
    PUBLISHER = "publisher"
    COMPATIBILITY = "compatibility"
    INSTALLATION = "installation"
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
    """What an audit row records (docs/059 "AUDIT")."""

    PLUGIN_REGISTERED = "plugin_registered"
    PLUGIN_PUBLISHED = "plugin_published"
    PLUGIN_INSTALLED = "plugin_installed"
    PLUGIN_ACTIVATED = "plugin_activated"
    PLUGIN_UPGRADED = "plugin_upgraded"
    PLUGIN_ROLLED_BACK = "plugin_rolled_back"
    PLUGIN_DISABLED = "plugin_disabled"
    PLUGIN_REMOVED = "plugin_removed"
    PERMISSION_GRANTED = "permission_granted"
    PERMISSION_REVOKED = "permission_revoked"
    ADMINISTRATIVE = "administrative"


__all__ = [
    "AuditAction",
    "InstallationTrigger",
    "ManifestValidationStatus",
    "MarketplaceListingStatus",
    "PackageFormat",
    "PermissionGrantStatus",
    "PluginCategory",
    "PluginInstallationStatus",
    "PluginLifecycleStatus",
    "PluginPermissionCategory",
    "PluginType",
    "PublisherType",
    "PublisherVerificationStatus",
    "ReportFormat",
    "ReportKind",
    "ReportStatus",
    "ReviewStatus",
    "RollbackStatus",
    "SignatureAlgorithm",
    "UpgradeStatus",
    "UpgradeStrategy",
]
