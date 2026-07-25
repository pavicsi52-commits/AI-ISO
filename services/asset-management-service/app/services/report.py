"""Report generation. Per docs/038 "REPORTING" "Generate": Asset, Cost,
Compliance, Warranty, Maintenance, Risk, Lifecycle Reports, Executive
Dashboards.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from shared_core.exceptions.validation import ValidationError

from app.models.asset_report import AssetReport
from app.models.enums import ReportType
from app.repositories.asset_report import AssetReportRepository
from app.services.compliance import ComplianceService
from app.services.cost import CostService
from app.services.lifecycle import LifecycleService
from app.services.maintenance import MaintenanceService
from app.services.managed_asset import ManagedAssetService
from app.services.risk import RiskService
from app.services.statistics import AssetStatisticsService
from app.services.warranty import WarrantyService


class ReportService:
    """Generates and lists asset-management reports."""

    def __init__(
        self,
        reports: AssetReportRepository,
        managed_assets: ManagedAssetService,
        costs: CostService,
        compliance: ComplianceService,
        warranty: WarrantyService,
        maintenance: MaintenanceService,
        risk: RiskService,
        lifecycle: LifecycleService,
        statistics: AssetStatisticsService,
    ) -> None:
        self._reports = reports
        self._managed_assets = managed_assets
        self._costs = costs
        self._compliance = compliance
        self._warranty = warranty
        self._maintenance = maintenance
        self._risk = risk
        self._lifecycle = lifecycle
        self._statistics = statistics

    async def list_for_org(
        self, organization_id: UUID, *, report_type: ReportType | None = None
    ) -> list[AssetReport]:
        """Every generated report for *organization_id* ("Generate")."""
        return await self._reports.list_for_org(organization_id, report_type=report_type)

    async def _asset_report(self, managed_asset_id: UUID) -> dict[str, Any]:
        managed_asset = await self._managed_assets.get_by_id(managed_asset_id)
        return {
            "business_name": managed_asset.business_name,
            "status": str(managed_asset.status),
            "lifecycle_state": str(managed_asset.lifecycle_state),
            "criticality": str(managed_asset.criticality),
            "operational_health": str(managed_asset.operational_health),
        }

    async def _cost_report(self, managed_asset_id: UUID) -> dict[str, Any]:
        total, by_type, _entries = await self._costs.get_total_cost_of_ownership(managed_asset_id)
        return {"total_cost_of_ownership": total, "by_cost_type": by_type}

    async def _compliance_report(self, managed_asset_id: UUID) -> dict[str, Any]:
        managed_asset = await self._managed_assets.get_by_id(managed_asset_id)
        entries = await self._compliance.list_for_managed_asset(managed_asset_id)
        return {
            "compliance_status": str(managed_asset.compliance_status),
            "evaluations": [str(entry.status) for entry in entries],
        }

    async def _warranty_report(self, managed_asset_id: UUID) -> dict[str, Any]:
        managed_asset = await self._managed_assets.get_by_id(managed_asset_id)
        entries = await self._warranty.list_for_managed_asset(managed_asset_id)
        return {"warranty_status": str(managed_asset.warranty_status), "periods": len(entries)}

    async def _maintenance_report(self, managed_asset_id: UUID) -> dict[str, Any]:
        entries = await self._maintenance.list_for_managed_asset(managed_asset_id)
        return {
            "total_activities": len(entries),
            "by_status": {
                str(status): sum(1 for e in entries if e.status == status)
                for status in {e.status for e in entries}
            },
        }

    async def _risk_report(self, managed_asset_id: UUID) -> dict[str, Any]:
        managed_asset = await self._managed_assets.get_by_id(managed_asset_id)
        entries = await self._risk.list_for_managed_asset(managed_asset_id)
        return {"risk_score": float(managed_asset.risk_score), "evaluations": len(entries)}

    async def _lifecycle_report(self, managed_asset_id: UUID) -> dict[str, Any]:
        managed_asset = await self._managed_assets.get_by_id(managed_asset_id)
        entries = await self._lifecycle.list_history(managed_asset_id)
        return {
            "lifecycle_state": str(managed_asset.lifecycle_state),
            "events": [entry.event_type for entry in entries],
        }

    async def _executive_dashboard_report(self, organization_id: UUID) -> dict[str, Any]:
        snapshot = await self._statistics.get_for_org(organization_id)
        return {
            "total_managed_assets": snapshot.total_managed_assets,
            "status_distribution": snapshot.status_distribution,
            "risk_distribution": snapshot.risk_distribution,
            "compliance_distribution": snapshot.compliance_distribution,
            "cost_trends": snapshot.cost_trends,
        }

    async def _build_result(
        self, organization_id: UUID, *, report_type: ReportType, managed_asset_id: UUID | None
    ) -> dict[str, Any]:
        if report_type == ReportType.EXECUTIVE_DASHBOARD:
            return await self._executive_dashboard_report(organization_id)
        if managed_asset_id is None:
            raise ValidationError(f"Report type {report_type!r} requires a managed_asset_id.")

        builders: dict[ReportType, Callable[[UUID], Awaitable[dict[str, Any]]]] = {
            ReportType.ASSET: self._asset_report,
            ReportType.COST: self._cost_report,
            ReportType.COMPLIANCE: self._compliance_report,
            ReportType.WARRANTY: self._warranty_report,
            ReportType.MAINTENANCE: self._maintenance_report,
            ReportType.RISK: self._risk_report,
            ReportType.LIFECYCLE: self._lifecycle_report,
        }
        return await builders[report_type](managed_asset_id)

    async def generate(
        self,
        organization_id: UUID,
        *,
        report_type: ReportType,
        managed_asset_id: UUID | None,
        parameters: dict[str, Any],
        generated_by: UUID | None,
    ) -> AssetReport:
        """Generate and persist a report ("Generate")."""
        result = await self._build_result(
            organization_id, report_type=report_type, managed_asset_id=managed_asset_id
        )
        return await self._reports.create(
            AssetReport(
                organization_id=organization_id,
                managed_asset_id=managed_asset_id,
                report_type=report_type,
                generated_by=generated_by,
                parameters=parameters,
                result=result,
                generated_at=datetime.now(UTC),
            )
        )


__all__ = ["ReportService"]
