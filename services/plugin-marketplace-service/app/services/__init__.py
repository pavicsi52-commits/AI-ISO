"""Every service this application owns."""

from __future__ import annotations

from app.services.dependency import PluginDependencyService
from app.services.health import PluginHealthService
from app.services.installation import PluginInstallationService
from app.services.marketplace import PluginMarketplaceService
from app.services.package import PluginPackageService
from app.services.permission import PluginPermissionService
from app.services.plugin import PluginService
from app.services.publisher import PluginPublisherService
from app.services.reporting import AuditService, ReportService, StatisticsService
from app.services.review import PluginReviewService

__all__ = [
    "AuditService",
    "PluginDependencyService",
    "PluginHealthService",
    "PluginInstallationService",
    "PluginMarketplaceService",
    "PluginPackageService",
    "PluginPermissionService",
    "PluginPublisherService",
    "PluginReviewService",
    "PluginService",
    "ReportService",
    "StatisticsService",
]
