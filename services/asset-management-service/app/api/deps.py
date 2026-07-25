"""FastAPI dependency injection for the asset management service.

One factory function per business service, each building its own
repositories from the request-scoped database session -- routes depend
on services only, never repositories directly. Matches
``services/inventory-service/app/api/deps.py``'s established shape,
with the addition of :func:`get_dependency_graph_client` (this
service's own read-only Neo4j integration, mirroring that service's
``get_topology_graph_client``) and :func:`get_caller_token`/
:func:`get_inventory_client` (mirroring ``services/discovery-service``'s
own cross-service-call precedent).
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Annotated
from uuid import UUID

import httpx
from fastapi import Depends, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from neo4j import AsyncDriver
from shared_core.database.session import session_scope
from shared_core.exceptions.authentication import AuthenticationError
from shared_core.notifications.manager import NotificationManager
from shared_core.security.jwt import decode_token
from sqlalchemy.ext.asyncio import AsyncSession

from app.assets.inventory_client import InventoryClient
from app.dependencies.graph_client import DependencyGraphClient
from app.notifications.asset_notifications import AssetNotificationService
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

_bearer_scheme = HTTPBearer(auto_error=False)


async def get_db_session(request: Request) -> AsyncIterator[AsyncSession]:
    """Yield a request-scoped database session, committing on success."""
    session_factory = request.app.state.db_session_factory
    async with session_scope(session_factory) as session:
        yield session


DbSession = Annotated[AsyncSession, Depends(get_db_session)]


def get_neo4j_driver(request: Request) -> AsyncDriver:
    """The process-wide Neo4j :class:`~neo4j.AsyncDriver`."""
    return request.app.state.neo4j_driver  # type: ignore[no-any-return]


def get_dependency_graph_client(
    driver: Annotated[AsyncDriver, Depends(get_neo4j_driver)],
) -> DependencyGraphClient:
    """The current request's :class:`DependencyGraphClient`."""
    return DependencyGraphClient(driver)


def get_notification_manager(request: Request) -> NotificationManager:
    """The process-wide :class:`NotificationManager`."""
    return request.app.state.notification_manager  # type: ignore[no-any-return]


def get_http_client(request: Request) -> httpx.AsyncClient:
    """The process-wide :class:`httpx.AsyncClient` shared by every
    cross-service call this service makes (Inventory Service lookups).
    """
    return request.app.state.http_client  # type: ignore[no-any-return]


async def get_current_user_id(
    request: Request,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer_scheme)],
) -> UUID:
    """Resolve the calling user's id from a Bearer token issued by
    ``services/authentication-service``.

    Raises:
        AuthenticationError: If no valid Bearer token is presented.
    """
    if credentials is None:
        raise AuthenticationError("Authentication required.")
    public_key = request.app.state.jwt_public_key
    claims = decode_token(credentials.credentials, public_key=public_key)
    return UUID(str(claims["sub"]))


CurrentUserId = Annotated[UUID, Depends(get_current_user_id)]


async def get_caller_token(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer_scheme)],
) -> str:
    """The raw Bearer token string, forwarded to the Inventory Service on
    this caller's behalf -- see ``app/assets/inventory_client.py``.

    Raises:
        AuthenticationError: If no valid Bearer token is presented.
    """
    if credentials is None:
        raise AuthenticationError("Authentication required.")
    return credentials.credentials


CurrentUserToken = Annotated[str, Depends(get_caller_token)]


def get_notification_service(
    manager: Annotated[NotificationManager, Depends(get_notification_manager)],
) -> AssetNotificationService:
    """The current request's :class:`AssetNotificationService`."""
    return AssetNotificationService(manager)


def get_inventory_client(
    client: Annotated[httpx.AsyncClient, Depends(get_http_client)], request: Request
) -> InventoryClient:
    """The current request's :class:`InventoryClient`."""
    settings = request.app.state.service_settings
    return InventoryClient(client, base_url=settings.inventory_service_base_url)


InventoryClientDep = Annotated[InventoryClient, Depends(get_inventory_client)]


def get_audit_service(session: DbSession) -> AssetAuditService:
    """The current request's :class:`AssetAuditService`."""
    return AssetAuditService(AssetAuditRepository(session))


AuditSvc = Annotated[AssetAuditService, Depends(get_audit_service)]


def get_lifecycle_service(request: Request, session: DbSession) -> LifecycleService:
    """The current request's fully-wired :class:`LifecycleService`."""
    return LifecycleService(
        ManagedAssetRepository(session),
        AssetChangeHistoryRepository(session),
        AssetRetirementRepository(session),
        publish_event=getattr(request.app.state, "publish_event", None),
    )


LifecycleSvc = Annotated[LifecycleService, Depends(get_lifecycle_service)]


def get_managed_asset_service(
    request: Request, session: DbSession, lifecycle: LifecycleSvc, audit: AuditSvc
) -> ManagedAssetService:
    """The current request's fully-wired :class:`ManagedAssetService`."""
    return ManagedAssetService(
        ManagedAssetRepository(session),
        lifecycle,
        audit,
        publish_event=getattr(request.app.state, "publish_event", None),
    )


ManagedAssetSvc = Annotated[ManagedAssetService, Depends(get_managed_asset_service)]


def get_assignment_service(request: Request, session: DbSession) -> AssetAssignmentService:
    """The current request's fully-wired :class:`AssetAssignmentService`."""
    return AssetAssignmentService(
        AssetAssignmentRepository(session),
        publish_event=getattr(request.app.state, "publish_event", None),
    )


AssignmentSvc = Annotated[AssetAssignmentService, Depends(get_assignment_service)]


def get_ownership_service(request: Request, session: DbSession) -> OwnershipService:
    """The current request's fully-wired :class:`OwnershipService`."""
    return OwnershipService(
        AssetOwnerRepository(session),
        AssetContactRepository(session),
        publish_event=getattr(request.app.state, "publish_event", None),
    )


OwnershipSvc = Annotated[OwnershipService, Depends(get_ownership_service)]


def get_warranty_service(request: Request, session: DbSession) -> WarrantyService:
    """The current request's fully-wired :class:`WarrantyService`."""
    return WarrantyService(
        AssetWarrantyRepository(session),
        ManagedAssetRepository(session),
        publish_event=getattr(request.app.state, "publish_event", None),
    )


WarrantySvc = Annotated[WarrantyService, Depends(get_warranty_service)]


def get_contract_service(request: Request, session: DbSession) -> ContractService:
    """The current request's fully-wired :class:`ContractService`."""
    return ContractService(
        AssetContractRepository(session),
        AssetVendorRepository(session),
        publish_event=getattr(request.app.state, "publish_event", None),
    )


ContractSvc = Annotated[ContractService, Depends(get_contract_service)]


def get_procurement_service(session: DbSession) -> ProcurementService:
    """The current request's :class:`ProcurementService`."""
    return ProcurementService(
        AssetProcurementRepository(session), AssetDepreciationRepository(session)
    )


ProcurementSvc = Annotated[ProcurementService, Depends(get_procurement_service)]


def get_cost_service(session: DbSession) -> CostService:
    """The current request's :class:`CostService`."""
    return CostService(AssetCostRepository(session), AssetBudgetRepository(session))


CostSvc = Annotated[CostService, Depends(get_cost_service)]


def get_maintenance_service(request: Request, session: DbSession) -> MaintenanceService:
    """The current request's fully-wired :class:`MaintenanceService`."""
    return MaintenanceService(
        AssetMaintenanceRepository(session),
        AssetMaintenanceWindowRepository(session),
        AssetMaintenanceHistoryRepository(session),
        publish_event=getattr(request.app.state, "publish_event", None),
    )


MaintenanceSvc = Annotated[MaintenanceService, Depends(get_maintenance_service)]


def get_firmware_service(session: DbSession, lifecycle: LifecycleSvc) -> FirmwareService:
    """The current request's fully-wired :class:`FirmwareService`."""
    return FirmwareService(AssetFirmwareRepository(session), lifecycle)


FirmwareSvc = Annotated[FirmwareService, Depends(get_firmware_service)]


def get_software_service(session: DbSession) -> SoftwareService:
    """The current request's :class:`SoftwareService`."""
    return SoftwareService(AssetSoftwareRepository(session), AssetPatchHistoryRepository(session))


SoftwareSvc = Annotated[SoftwareService, Depends(get_software_service)]


def get_compliance_service(request: Request, session: DbSession) -> ComplianceService:
    """The current request's fully-wired :class:`ComplianceService`."""
    return ComplianceService(
        AssetComplianceRepository(session),
        ManagedAssetRepository(session),
        publish_event=getattr(request.app.state, "publish_event", None),
    )


ComplianceSvc = Annotated[ComplianceService, Depends(get_compliance_service)]


def get_risk_service(request: Request, session: DbSession) -> RiskService:
    """The current request's fully-wired :class:`RiskService`."""
    return RiskService(
        AssetRiskRepository(session),
        ManagedAssetRepository(session),
        publish_event=getattr(request.app.state, "publish_event", None),
    )


RiskSvc = Annotated[RiskService, Depends(get_risk_service)]


def get_health_service(session: DbSession) -> HealthService:
    """The current request's :class:`HealthService`."""
    return HealthService(AssetHealthRollupRepository(session), ManagedAssetRepository(session))


HealthSvc = Annotated[HealthService, Depends(get_health_service)]


def get_dependency_service(
    session: DbSession,
    graph: Annotated[DependencyGraphClient, Depends(get_dependency_graph_client)],
) -> DependencyService:
    """The current request's fully-wired :class:`DependencyService`."""
    return DependencyService(
        AssetDependencyAnalysisRepository(session), ManagedAssetRepository(session), graph
    )


DependencySvc = Annotated[DependencyService, Depends(get_dependency_service)]


def get_statistics_service(session: DbSession) -> AssetStatisticsService:
    """The current request's :class:`AssetStatisticsService`."""
    return AssetStatisticsService(
        AssetStatisticsRepository(session),
        ManagedAssetRepository(session),
        AssetCostRepository(session),
        AssetMaintenanceRepository(session),
        AssetVendorRepository(session),
    )


StatisticsSvc = Annotated[AssetStatisticsService, Depends(get_statistics_service)]


def get_report_service(
    session: DbSession,
    managed_assets: ManagedAssetSvc,
    costs: CostSvc,
    compliance: ComplianceSvc,
    warranty: WarrantySvc,
    maintenance: MaintenanceSvc,
    risk: RiskSvc,
    lifecycle: LifecycleSvc,
    statistics: StatisticsSvc,
) -> ReportService:
    """The current request's fully-wired :class:`ReportService`."""
    return ReportService(
        AssetReportRepository(session),
        managed_assets,
        costs,
        compliance,
        warranty,
        maintenance,
        risk,
        lifecycle,
        statistics,
    )


ReportSvc = Annotated[ReportService, Depends(get_report_service)]

__all__ = [
    "AssignmentSvc",
    "AuditSvc",
    "ComplianceSvc",
    "ContractSvc",
    "CostSvc",
    "CurrentUserId",
    "CurrentUserToken",
    "DbSession",
    "DependencySvc",
    "FirmwareSvc",
    "HealthSvc",
    "InventoryClientDep",
    "LifecycleSvc",
    "MaintenanceSvc",
    "ManagedAssetSvc",
    "OwnershipSvc",
    "ProcurementSvc",
    "ReportSvc",
    "RiskSvc",
    "SoftwareSvc",
    "StatisticsSvc",
    "WarrantySvc",
    "get_assignment_service",
    "get_audit_service",
    "get_caller_token",
    "get_compliance_service",
    "get_contract_service",
    "get_cost_service",
    "get_current_user_id",
    "get_db_session",
    "get_dependency_graph_client",
    "get_dependency_service",
    "get_firmware_service",
    "get_health_service",
    "get_http_client",
    "get_inventory_client",
    "get_lifecycle_service",
    "get_maintenance_service",
    "get_managed_asset_service",
    "get_neo4j_driver",
    "get_notification_manager",
    "get_notification_service",
    "get_ownership_service",
    "get_procurement_service",
    "get_report_service",
    "get_risk_service",
    "get_software_service",
    "get_statistics_service",
    "get_warranty_service",
]
