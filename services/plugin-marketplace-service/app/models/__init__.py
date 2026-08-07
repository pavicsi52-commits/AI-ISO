"""All ORM models and enums this service persists, re-exported for a
single import surface (``from app.models import Plugin, PluginCategory``).
"""

from __future__ import annotations

from shared_core.enums.health_status import HealthStatus

from app.models.dependency import PluginDependency
from app.models.enums import (
    AuditAction,
    InstallationTrigger,
    ManifestValidationStatus,
    MarketplaceListingStatus,
    PackageFormat,
    PermissionGrantStatus,
    PluginCategory,
    PluginInstallationStatus,
    PluginLifecycleStatus,
    PluginPermissionCategory,
    PluginType,
    PublisherType,
    PublisherVerificationStatus,
    ReportFormat,
    ReportKind,
    ReportStatus,
    ReviewStatus,
    RollbackStatus,
    SignatureAlgorithm,
    UpgradeStatus,
    UpgradeStrategy,
)
from app.models.governance import PluginAudit, PluginReport, PluginStatistic
from app.models.health import PluginHealth
from app.models.installation import PluginInstallation
from app.models.manifest import PluginManifestEntry
from app.models.marketplace import PluginMarketplaceEntry
from app.models.package import PluginPackage
from app.models.permission import PluginPermissionGrant
from app.models.plugin import Plugin, PluginVersion
from app.models.publisher import PluginPublisher
from app.models.review import PluginRating, PluginReview
from app.models.upgrade import PluginRollback, PluginUpgrade

__all__ = [
    "AuditAction",
    "HealthStatus",
    "InstallationTrigger",
    "ManifestValidationStatus",
    "MarketplaceListingStatus",
    "PackageFormat",
    "PermissionGrantStatus",
    "Plugin",
    "PluginAudit",
    "PluginCategory",
    "PluginDependency",
    "PluginHealth",
    "PluginInstallation",
    "PluginInstallationStatus",
    "PluginLifecycleStatus",
    "PluginManifestEntry",
    "PluginMarketplaceEntry",
    "PluginPackage",
    "PluginPermissionCategory",
    "PluginPermissionGrant",
    "PluginPublisher",
    "PluginRating",
    "PluginReport",
    "PluginReview",
    "PluginRollback",
    "PluginStatistic",
    "PluginType",
    "PluginUpgrade",
    "PluginVersion",
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
