"""Repositories for the discovery service, one per model."""

from __future__ import annotations

from app.repositories.discovery_asset import DiscoveryAssetRepository
from app.repositories.discovery_audit import DiscoveryAuditRepository
from app.repositories.discovery_classification import DiscoveryClassificationRepository
from app.repositories.discovery_credential import DiscoveryCredentialRepository
from app.repositories.discovery_failure import DiscoveryFailureRepository
from app.repositories.discovery_filter import DiscoveryFilterRepository
from app.repositories.discovery_history import DiscoveryHistoryRepository
from app.repositories.discovery_job import DiscoveryJobRepository
from app.repositories.discovery_profile import DiscoveryProfileRepository
from app.repositories.discovery_relationship import DiscoveryRelationshipRepository
from app.repositories.discovery_result import DiscoveryResultRepository
from app.repositories.discovery_rule import DiscoveryRuleRepository
from app.repositories.discovery_schedule import DiscoveryScheduleRepository
from app.repositories.discovery_statistics import DiscoveryStatisticsRepository
from app.repositories.discovery_target import DiscoveryTargetRepository

__all__ = [
    "DiscoveryAssetRepository",
    "DiscoveryAuditRepository",
    "DiscoveryClassificationRepository",
    "DiscoveryCredentialRepository",
    "DiscoveryFailureRepository",
    "DiscoveryFilterRepository",
    "DiscoveryHistoryRepository",
    "DiscoveryJobRepository",
    "DiscoveryProfileRepository",
    "DiscoveryRelationshipRepository",
    "DiscoveryResultRepository",
    "DiscoveryRuleRepository",
    "DiscoveryScheduleRepository",
    "DiscoveryStatisticsRepository",
    "DiscoveryTargetRepository",
]
