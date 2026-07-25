"""Repositories for the asset management service, one per model."""

from __future__ import annotations

from app.repositories.asset_assignment import AssetAssignmentRepository
from app.repositories.asset_audit import AssetAuditRepository
from app.repositories.asset_budget import AssetBudgetRepository
from app.repositories.asset_change_history import AssetChangeHistoryRepository
from app.repositories.asset_compliance import AssetComplianceRepository
from app.repositories.asset_contact import AssetContactRepository
from app.repositories.asset_contract import AssetContractRepository
from app.repositories.asset_cost import AssetCostRepository
from app.repositories.asset_dependency_analysis import AssetDependencyAnalysisRepository
from app.repositories.asset_depreciation import AssetDepreciationRepository
from app.repositories.asset_firmware import AssetFirmwareRepository
from app.repositories.asset_health_rollup import AssetHealthRollupRepository
from app.repositories.asset_maintenance import AssetMaintenanceRepository
from app.repositories.asset_maintenance_history import AssetMaintenanceHistoryRepository
from app.repositories.asset_maintenance_window import AssetMaintenanceWindowRepository
from app.repositories.asset_owner import AssetOwnerRepository
from app.repositories.asset_patch_history import AssetPatchHistoryRepository
from app.repositories.asset_procurement import AssetProcurementRepository
from app.repositories.asset_report import AssetReportRepository
from app.repositories.asset_retirement import AssetRetirementRepository
from app.repositories.asset_risk import AssetRiskRepository
from app.repositories.asset_software import AssetSoftwareRepository
from app.repositories.asset_statistics import AssetStatisticsRepository
from app.repositories.asset_vendor import AssetVendorRepository
from app.repositories.asset_warranty import AssetWarrantyRepository
from app.repositories.managed_asset import ManagedAssetRepository

__all__ = [
    "AssetAssignmentRepository",
    "AssetAuditRepository",
    "AssetBudgetRepository",
    "AssetChangeHistoryRepository",
    "AssetComplianceRepository",
    "AssetContactRepository",
    "AssetContractRepository",
    "AssetCostRepository",
    "AssetDependencyAnalysisRepository",
    "AssetDepreciationRepository",
    "AssetFirmwareRepository",
    "AssetHealthRollupRepository",
    "AssetMaintenanceHistoryRepository",
    "AssetMaintenanceRepository",
    "AssetMaintenanceWindowRepository",
    "AssetOwnerRepository",
    "AssetPatchHistoryRepository",
    "AssetProcurementRepository",
    "AssetReportRepository",
    "AssetRetirementRepository",
    "AssetRiskRepository",
    "AssetSoftwareRepository",
    "AssetStatisticsRepository",
    "AssetVendorRepository",
    "AssetWarrantyRepository",
    "ManagedAssetRepository",
]
