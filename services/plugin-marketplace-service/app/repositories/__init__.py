"""Every repository this service owns.

Each is tenant-scoped. The scoped lookups are named ``require_in_org``
rather than overriding the base ``require_by_id`` -- two same-named
methods of different arity on one class make an unscoped call look
correct, which is how a cross-tenant read gets written.
"""

from __future__ import annotations

from app.repositories.dependency import PluginDependencyRepository
from app.repositories.governance import (
    PluginAuditRepository,
    PluginReportRepository,
    PluginStatisticRepository,
)
from app.repositories.health import PluginHealthRepository
from app.repositories.installation import PluginInstallationRepository
from app.repositories.manifest import PluginManifestRepository
from app.repositories.marketplace import PluginMarketplaceRepository
from app.repositories.package import PluginPackageRepository
from app.repositories.permission import PluginPermissionRepository
from app.repositories.plugin import PluginRepository, PluginVersionRepository
from app.repositories.publisher import PluginPublisherRepository
from app.repositories.review import PluginRatingRepository, PluginReviewRepository
from app.repositories.upgrade import PluginRollbackRepository, PluginUpgradeRepository

__all__ = [
    "PluginAuditRepository",
    "PluginDependencyRepository",
    "PluginHealthRepository",
    "PluginInstallationRepository",
    "PluginManifestRepository",
    "PluginMarketplaceRepository",
    "PluginPackageRepository",
    "PluginPermissionRepository",
    "PluginPublisherRepository",
    "PluginRatingRepository",
    "PluginReportRepository",
    "PluginRepository",
    "PluginReviewRepository",
    "PluginRollbackRepository",
    "PluginStatisticRepository",
    "PluginUpgradeRepository",
    "PluginVersionRepository",
]
