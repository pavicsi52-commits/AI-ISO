"""SQLAlchemy models for the inventory service, one per table.

Importing this module registers every table with
:data:`shared_core.database.base.Base.metadata`, which Alembic's
``env.py`` depends on for autogenerate support.
"""

from __future__ import annotations

from app.models.asset import Asset
from app.models.asset_attribute import AssetAttribute
from app.models.asset_category import AssetCategory
from app.models.asset_class import AssetClass
from app.models.asset_contact import AssetContact
from app.models.asset_custom_field import AssetCustomField
from app.models.asset_discovery_link import AssetDiscoveryLink
from app.models.asset_export_job import AssetExportJob
from app.models.asset_group import AssetGroup
from app.models.asset_health_history import AssetHealthHistoryEntry
from app.models.asset_history import AssetHistoryEntry
from app.models.asset_import_job import AssetImportJob
from app.models.asset_label import AssetLabel
from app.models.asset_lifecycle_history import AssetLifecycleHistoryEntry
from app.models.asset_location import AssetLocation
from app.models.asset_metadata import AssetMetadataEntry
from app.models.asset_owner import AssetOwner
from app.models.asset_relationship import AssetRelationship
from app.models.asset_status_history import AssetStatusHistoryEntry
from app.models.asset_tag import AssetTag
from app.models.asset_topology_cache import AssetTopologyCacheEntry
from app.models.asset_type import AssetTypeDefinition
from app.models.asset_version import AssetVersion
from app.models.inventory_audit import InventoryAuditEntry
from app.models.inventory_statistics import InventoryStatistics

__all__ = [
    "Asset",
    "AssetAttribute",
    "AssetCategory",
    "AssetClass",
    "AssetContact",
    "AssetCustomField",
    "AssetDiscoveryLink",
    "AssetExportJob",
    "AssetGroup",
    "AssetHealthHistoryEntry",
    "AssetHistoryEntry",
    "AssetImportJob",
    "AssetLabel",
    "AssetLifecycleHistoryEntry",
    "AssetLocation",
    "AssetMetadataEntry",
    "AssetOwner",
    "AssetRelationship",
    "AssetStatusHistoryEntry",
    "AssetTag",
    "AssetTopologyCacheEntry",
    "AssetTypeDefinition",
    "AssetVersion",
    "InventoryAuditEntry",
    "InventoryStatistics",
]
