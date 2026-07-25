"""Repositories for the inventory service, one per model."""

from __future__ import annotations

from app.repositories.asset import AssetRepository
from app.repositories.asset_attribute import AssetAttributeRepository
from app.repositories.asset_category import AssetCategoryRepository
from app.repositories.asset_class import AssetClassRepository
from app.repositories.asset_contact import AssetContactRepository
from app.repositories.asset_custom_field import AssetCustomFieldRepository
from app.repositories.asset_discovery_link import AssetDiscoveryLinkRepository
from app.repositories.asset_export_job import AssetExportJobRepository
from app.repositories.asset_group import AssetGroupRepository
from app.repositories.asset_health_history import AssetHealthHistoryRepository
from app.repositories.asset_history import AssetHistoryRepository
from app.repositories.asset_import_job import AssetImportJobRepository
from app.repositories.asset_label import AssetLabelRepository
from app.repositories.asset_lifecycle_history import AssetLifecycleHistoryRepository
from app.repositories.asset_location import AssetLocationRepository
from app.repositories.asset_metadata import AssetMetadataRepository
from app.repositories.asset_owner import AssetOwnerRepository
from app.repositories.asset_relationship import AssetRelationshipRepository
from app.repositories.asset_status_history import AssetStatusHistoryRepository
from app.repositories.asset_tag import AssetTagRepository
from app.repositories.asset_topology_cache import AssetTopologyCacheRepository
from app.repositories.asset_type import AssetTypeDefinitionRepository
from app.repositories.asset_version import AssetVersionRepository
from app.repositories.inventory_audit import InventoryAuditRepository
from app.repositories.inventory_statistics import InventoryStatisticsRepository

__all__ = [
    "AssetAttributeRepository",
    "AssetCategoryRepository",
    "AssetClassRepository",
    "AssetContactRepository",
    "AssetCustomFieldRepository",
    "AssetDiscoveryLinkRepository",
    "AssetExportJobRepository",
    "AssetGroupRepository",
    "AssetHealthHistoryRepository",
    "AssetHistoryRepository",
    "AssetImportJobRepository",
    "AssetLabelRepository",
    "AssetLifecycleHistoryRepository",
    "AssetLocationRepository",
    "AssetMetadataRepository",
    "AssetOwnerRepository",
    "AssetRelationshipRepository",
    "AssetRepository",
    "AssetStatusHistoryRepository",
    "AssetTagRepository",
    "AssetTopologyCacheRepository",
    "AssetTypeDefinitionRepository",
    "AssetVersionRepository",
    "InventoryAuditRepository",
    "InventoryStatisticsRepository",
]
