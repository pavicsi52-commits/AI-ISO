"""SQLAlchemy models for the discovery service, one per table."""

from __future__ import annotations

from app.models.discovery_asset import DiscoveryAsset
from app.models.discovery_audit import DiscoveryAuditEntry
from app.models.discovery_classification import DiscoveryClassificationEntry
from app.models.discovery_credential import DiscoveryCredential
from app.models.discovery_failure import DiscoveryFailure
from app.models.discovery_filter import DiscoveryFilter
from app.models.discovery_history import DiscoveryHistoryEntry
from app.models.discovery_job import DiscoveryJob
from app.models.discovery_profile import DiscoveryProfile
from app.models.discovery_relationship import DiscoveryRelationship
from app.models.discovery_result import DiscoveryResult
from app.models.discovery_rule import DiscoveryRule
from app.models.discovery_schedule import DiscoverySchedule
from app.models.discovery_statistics import DiscoveryStatistics
from app.models.discovery_target import DiscoveryTarget

__all__ = [
    "DiscoveryAsset",
    "DiscoveryAuditEntry",
    "DiscoveryClassificationEntry",
    "DiscoveryCredential",
    "DiscoveryFailure",
    "DiscoveryFilter",
    "DiscoveryHistoryEntry",
    "DiscoveryJob",
    "DiscoveryProfile",
    "DiscoveryRelationship",
    "DiscoveryResult",
    "DiscoveryRule",
    "DiscoverySchedule",
    "DiscoveryStatistics",
    "DiscoveryTarget",
]
