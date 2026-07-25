"""Business services for the asset management service, one per domain area."""

from __future__ import annotations

from app.services.assignment import AssetAssignmentService
from app.services.audit import AssetAuditService
from app.services.compliance import ComplianceService
from app.services.contract import ContractService
from app.services.cost import CostService
from app.services.dependency import DependencyService
from app.services.firmware import FirmwareService
from app.services.health import HealthService
from app.services.lifecycle import LifecycleService
from app.services.maintenance import MaintenanceService
from app.services.managed_asset import ManagedAssetService
from app.services.ownership import OwnershipService
from app.services.procurement import ProcurementService
from app.services.report import ReportService
from app.services.risk import RiskService
from app.services.software import SoftwareService
from app.services.statistics import AssetStatisticsService
from app.services.warranty import WarrantyService

__all__ = [
    "AssetAssignmentService",
    "AssetAuditService",
    "AssetStatisticsService",
    "ComplianceService",
    "ContractService",
    "CostService",
    "DependencyService",
    "FirmwareService",
    "HealthService",
    "LifecycleService",
    "MaintenanceService",
    "ManagedAssetService",
    "OwnershipService",
    "ProcurementService",
    "ReportService",
    "RiskService",
    "SoftwareService",
    "WarrantyService",
]
