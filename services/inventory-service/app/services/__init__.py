"""Business services for the inventory service, one per concern."""

from __future__ import annotations

from app.services.asset import AssetService
from app.services.asset_class import AssetClassService
from app.services.asset_type import AssetTypeDefinitionService
from app.services.attribute import AssetAttributeService
from app.services.audit import InventoryAuditService
from app.services.category import AssetCategoryService
from app.services.contact import AssetContactService
from app.services.custom_field import AssetCustomFieldService
from app.services.discovery_link import AssetDiscoveryLinkService
from app.services.export_service import AssetExportService
from app.services.group import AssetGroupService
from app.services.health_history import AssetHealthHistoryService
from app.services.history import AssetHistoryService
from app.services.import_service import AssetImportService
from app.services.label import AssetLabelService
from app.services.lifecycle_history import AssetLifecycleHistoryService
from app.services.location import AssetLocationService
from app.services.metadata import AssetMetadataService
from app.services.owner import AssetOwnerService
from app.services.relationship import AssetRelationshipService
from app.services.statistics import InventoryStatisticsService
from app.services.status_history import AssetStatusHistoryService
from app.services.tag import AssetTagService
from app.services.topology import TopologyService
from app.services.version import AssetVersionService

__all__ = [
    "AssetAttributeService",
    "AssetCategoryService",
    "AssetClassService",
    "AssetContactService",
    "AssetCustomFieldService",
    "AssetDiscoveryLinkService",
    "AssetExportService",
    "AssetGroupService",
    "AssetHealthHistoryService",
    "AssetHistoryService",
    "AssetImportService",
    "AssetLabelService",
    "AssetLifecycleHistoryService",
    "AssetLocationService",
    "AssetMetadataService",
    "AssetOwnerService",
    "AssetRelationshipService",
    "AssetService",
    "AssetStatusHistoryService",
    "AssetTagService",
    "AssetTypeDefinitionService",
    "AssetVersionService",
    "InventoryAuditService",
    "InventoryStatisticsService",
    "TopologyService",
]
