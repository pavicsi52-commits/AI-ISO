"""Tests for :class:`app.services.report.ReportService`."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

import pytest
from shared_core.exceptions.validation import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.enums import CostType, ReportType
from app.repositories.asset_audit import AssetAuditRepository
from app.repositories.asset_budget import AssetBudgetRepository
from app.repositories.asset_compliance import AssetComplianceRepository
from app.repositories.asset_cost import AssetCostRepository
from app.repositories.asset_maintenance import AssetMaintenanceRepository
from app.repositories.asset_maintenance_history import AssetMaintenanceHistoryRepository
from app.repositories.asset_maintenance_window import AssetMaintenanceWindowRepository
from app.repositories.asset_report import AssetReportRepository
from app.repositories.asset_risk import AssetRiskRepository
from app.repositories.asset_statistics import AssetStatisticsRepository
from app.repositories.asset_vendor import AssetVendorRepository
from app.repositories.asset_warranty import AssetWarrantyRepository
from app.repositories.managed_asset import ManagedAssetRepository
from app.services.audit import AssetAuditService
from app.services.compliance import ComplianceService
from app.services.cost import CostService
from app.services.maintenance import MaintenanceService
from app.services.managed_asset import ManagedAssetService
from app.services.report import ReportService
from app.services.risk import RiskService
from app.services.statistics import AssetStatisticsService
from app.services.warranty import WarrantyService
from tests.conftest import build_lifecycle_service, make_managed_asset


def _build(db_session: AsyncSession) -> tuple[ReportService, CostService]:
    lifecycle = build_lifecycle_service(db_session)
    managed_assets = ManagedAssetService(
        ManagedAssetRepository(db_session),
        lifecycle,
        AssetAuditService(AssetAuditRepository(db_session)),
    )
    costs = CostService(AssetCostRepository(db_session), AssetBudgetRepository(db_session))
    compliance = ComplianceService(
        AssetComplianceRepository(db_session), ManagedAssetRepository(db_session)
    )
    warranty = WarrantyService(
        AssetWarrantyRepository(db_session), ManagedAssetRepository(db_session)
    )
    maintenance = MaintenanceService(
        AssetMaintenanceRepository(db_session),
        AssetMaintenanceWindowRepository(db_session),
        AssetMaintenanceHistoryRepository(db_session),
    )
    risk = RiskService(AssetRiskRepository(db_session), ManagedAssetRepository(db_session))
    statistics = AssetStatisticsService(
        AssetStatisticsRepository(db_session),
        ManagedAssetRepository(db_session),
        AssetCostRepository(db_session),
        AssetMaintenanceRepository(db_session),
        AssetVendorRepository(db_session),
    )
    report_service = ReportService(
        AssetReportRepository(db_session),
        managed_assets,
        costs,
        compliance,
        warranty,
        maintenance,
        risk,
        lifecycle,
        statistics,
    )
    return report_service, costs


async def test_generate_asset_report(db_session: AsyncSession) -> None:
    managed_asset = await make_managed_asset(db_session)
    service, _costs = _build(db_session)

    report = await service.generate(
        managed_asset.organization_id,
        report_type=ReportType.ASSET,
        managed_asset_id=managed_asset.id,
        parameters={},
        generated_by=uuid.uuid4(),
    )

    assert report.result["business_name"] == managed_asset.business_name


async def test_generate_cost_report(db_session: AsyncSession) -> None:
    managed_asset = await make_managed_asset(db_session)
    service, costs = _build(db_session)
    await costs.record_cost(
        managed_asset.id,
        organization_id=managed_asset.organization_id,
        cost_type=CostType.CLOUD,
        amount=100.0,
        currency="USD",
        incurred_at=datetime.now(UTC),
        description=None,
    )

    report = await service.generate(
        managed_asset.organization_id,
        report_type=ReportType.COST,
        managed_asset_id=managed_asset.id,
        parameters={},
        generated_by=None,
    )

    assert report.result["total_cost_of_ownership"] == 100.0


async def test_generate_requires_managed_asset_id_for_asset_scoped_reports(
    db_session: AsyncSession,
) -> None:
    service, _costs = _build(db_session)
    with pytest.raises(ValidationError):
        await service.generate(
            uuid.uuid4(),
            report_type=ReportType.ASSET,
            managed_asset_id=None,
            parameters={},
            generated_by=None,
        )


async def test_generate_executive_dashboard_needs_no_managed_asset(
    db_session: AsyncSession,
) -> None:
    org_id = uuid.uuid4()
    await make_managed_asset(db_session, organization_id=org_id)
    service, _costs = _build(db_session)

    report = await service.generate(
        org_id,
        report_type=ReportType.EXECUTIVE_DASHBOARD,
        managed_asset_id=None,
        parameters={},
        generated_by=None,
    )

    assert report.result["total_managed_assets"] == 1


async def test_generate_compliance_warranty_maintenance_risk_lifecycle_reports(
    db_session: AsyncSession,
) -> None:
    managed_asset = await make_managed_asset(db_session)
    service, _costs = _build(db_session)

    for report_type in (
        ReportType.COMPLIANCE,
        ReportType.WARRANTY,
        ReportType.MAINTENANCE,
        ReportType.RISK,
        ReportType.LIFECYCLE,
    ):
        report = await service.generate(
            managed_asset.organization_id,
            report_type=report_type,
            managed_asset_id=managed_asset.id,
            parameters={"scope": "smoke"},
            generated_by=None,
        )
        assert report.report_type == report_type
        assert report.result is not None


async def test_list_for_org_filters_by_type(db_session: AsyncSession) -> None:
    managed_asset = await make_managed_asset(db_session)
    service, _costs = _build(db_session)
    await service.generate(
        managed_asset.organization_id,
        report_type=ReportType.ASSET,
        managed_asset_id=managed_asset.id,
        parameters={},
        generated_by=None,
    )
    await service.generate(
        managed_asset.organization_id,
        report_type=ReportType.RISK,
        managed_asset_id=managed_asset.id,
        parameters={},
        generated_by=None,
    )

    asset_reports = await service.list_for_org(
        managed_asset.organization_id, report_type=ReportType.ASSET
    )
    assert len(asset_reports) == 1
    assert asset_reports[0].report_type == ReportType.ASSET
