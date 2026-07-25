"""SQLAlchemy models for the asset management service, one per table.

Importing this module registers every table with
:data:`shared_core.database.base.Base.metadata`, which Alembic's
``env.py`` depends on for autogenerate support.
"""

from __future__ import annotations

from app.models.asset_assignment import AssetAssignment
from app.models.asset_audit import AssetAuditEntry
from app.models.asset_budget import AssetBudget
from app.models.asset_change_history import AssetChangeHistoryEntry
from app.models.asset_compliance import AssetCompliance
from app.models.asset_contact import AssetContact
from app.models.asset_contract import AssetContract
from app.models.asset_cost import AssetCost
from app.models.asset_dependency_analysis import AssetDependencyAnalysis
from app.models.asset_depreciation import AssetDepreciation
from app.models.asset_firmware import AssetFirmware
from app.models.asset_health_rollup import AssetHealthRollup
from app.models.asset_maintenance import AssetMaintenance
from app.models.asset_maintenance_history import AssetMaintenanceHistoryEntry
from app.models.asset_maintenance_window import AssetMaintenanceWindow
from app.models.asset_owner import AssetOwner
from app.models.asset_patch_history import AssetPatchHistoryEntry
from app.models.asset_procurement import AssetProcurement
from app.models.asset_report import AssetReport
from app.models.asset_retirement import AssetRetirement
from app.models.asset_risk import AssetRisk
from app.models.asset_software import AssetSoftware
from app.models.asset_statistics import AssetStatistics
from app.models.asset_vendor import AssetVendor
from app.models.asset_warranty import AssetWarranty
from app.models.managed_asset import ManagedAsset

__all__ = [
    "AssetAssignment",
    "AssetAuditEntry",
    "AssetBudget",
    "AssetChangeHistoryEntry",
    "AssetCompliance",
    "AssetContact",
    "AssetContract",
    "AssetCost",
    "AssetDependencyAnalysis",
    "AssetDepreciation",
    "AssetFirmware",
    "AssetHealthRollup",
    "AssetMaintenance",
    "AssetMaintenanceHistoryEntry",
    "AssetMaintenanceWindow",
    "AssetOwner",
    "AssetPatchHistoryEntry",
    "AssetProcurement",
    "AssetReport",
    "AssetRetirement",
    "AssetRisk",
    "AssetSoftware",
    "AssetStatistics",
    "AssetVendor",
    "AssetWarranty",
    "ManagedAsset",
]
