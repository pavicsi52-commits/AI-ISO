"""Business services for the discovery service, one per concern."""

from __future__ import annotations

from app.services.asset import DiscoveryAssetService
from app.services.audit import DiscoveryAuditService
from app.services.classification import DiscoveryClassificationService
from app.services.credential import DiscoveryCredentialService
from app.services.discovery_execution import DiscoveryExecutionService
from app.services.failure import DiscoveryFailureService
from app.services.filter import DiscoveryFilterService
from app.services.history import DiscoveryHistoryService
from app.services.job import DiscoveryJobService
from app.services.profile import DiscoveryProfileService
from app.services.relationship import DiscoveryRelationshipService
from app.services.result import DiscoveryResultService
from app.services.rule import DiscoveryRuleService
from app.services.schedule import DiscoveryScheduleService
from app.services.statistics import DiscoveryStatisticsService
from app.services.target import DiscoveryTargetService

__all__ = [
    "DiscoveryAssetService",
    "DiscoveryAuditService",
    "DiscoveryClassificationService",
    "DiscoveryCredentialService",
    "DiscoveryExecutionService",
    "DiscoveryFailureService",
    "DiscoveryFilterService",
    "DiscoveryHistoryService",
    "DiscoveryJobService",
    "DiscoveryProfileService",
    "DiscoveryRelationshipService",
    "DiscoveryResultService",
    "DiscoveryRuleService",
    "DiscoveryScheduleService",
    "DiscoveryStatisticsService",
    "DiscoveryTargetService",
]
