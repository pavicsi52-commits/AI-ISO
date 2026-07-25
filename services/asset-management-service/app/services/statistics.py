"""Asset management statistics/analytics computation. Per docs/038
"ANALYTICS" "Collect": Asset Growth, Operational Health, Maintenance
Trends, Compliance Trends, Risk Trends, Cost Trends, Vendor
Performance, Lifecycle Distribution. Computed on demand and cached,
the same "cached, not live" shape ``services/inventory-service``'s own
``inventory_statistics`` established.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from datetime import UTC, datetime, timedelta
from uuid import UUID

from app.models.asset_statistics import AssetStatistics
from app.models.managed_asset import ManagedAsset
from app.repositories.asset_cost import AssetCostRepository
from app.repositories.asset_maintenance import AssetMaintenanceRepository
from app.repositories.asset_statistics import AssetStatisticsRepository
from app.repositories.asset_vendor import AssetVendorRepository
from app.repositories.managed_asset import ManagedAssetRepository

_GROWTH_WINDOW = timedelta(days=30)
_RISK_CRITICAL_THRESHOLD = 75.0
_RISK_HIGH_THRESHOLD = 50.0
_RISK_MEDIUM_THRESHOLD = 25.0


def _risk_bucket(score: float) -> str:
    if score >= _RISK_CRITICAL_THRESHOLD:
        return "critical"
    if score >= _RISK_HIGH_THRESHOLD:
        return "high"
    if score >= _RISK_MEDIUM_THRESHOLD:
        return "medium"
    return "low"


class AssetStatisticsService:
    """Recomputes and reads an organization's cached asset-management analytics."""

    def __init__(
        self,
        statistics: AssetStatisticsRepository,
        managed_assets: ManagedAssetRepository,
        costs: AssetCostRepository,
        maintenance: AssetMaintenanceRepository,
        vendors: AssetVendorRepository,
    ) -> None:
        self._statistics = statistics
        self._managed_assets = managed_assets
        self._costs = costs
        self._maintenance = maintenance
        self._vendors = vendors

    async def get_for_org(self, organization_id: UUID) -> AssetStatistics:
        """Return *organization_id*'s cached snapshot, recomputing if none exists yet."""
        existing = await self._statistics.get_for_org(organization_id)
        if existing is not None:
            return existing
        return await self.recompute(organization_id)

    async def _cost_and_maintenance_trends(
        self, managed_assets: list[ManagedAsset]
    ) -> tuple[dict[str, float], dict[str, int]]:
        cost_totals: dict[str, float] = defaultdict(float)
        maintenance_totals: Counter[str] = Counter()
        for asset in managed_assets:
            for cost in await self._costs.list_for_managed_asset(asset.id):
                cost_totals[str(cost.cost_type)] += float(cost.amount)
            for activity in await self._maintenance.list_for_managed_asset(asset.id):
                maintenance_totals[str(activity.status)] += 1
        return dict(cost_totals), dict(maintenance_totals)

    async def _vendor_performance(
        self, organization_id: UUID, managed_assets: list[ManagedAsset]
    ) -> dict[str, int]:
        vendors = await self._vendors.list_for_org(organization_id)
        performance = {vendor.name: 0 for vendor in vendors}
        vendors_by_id = {vendor.id: vendor for vendor in vendors}
        for asset in managed_assets:
            vendor = vendors_by_id.get(asset.vendor_id) if asset.vendor_id else None
            if vendor is not None:
                performance[vendor.name] += 1
        return performance

    async def recompute(self, organization_id: UUID) -> AssetStatistics:
        """Recompute and persist *organization_id*'s statistics snapshot."""
        managed_assets = await self._managed_assets.list_for_org(organization_id)
        cutoff = datetime.now(UTC) - _GROWTH_WINDOW
        cost_trends, maintenance_trends = await self._cost_and_maintenance_trends(managed_assets)

        snapshot_fields = {
            "total_managed_assets": len(managed_assets),
            "asset_growth": {
                "total": len(managed_assets),
                "added_last_30_days": sum(
                    1 for asset in managed_assets if asset.created_at >= cutoff
                ),
            },
            "status_distribution": dict(Counter(str(a.status) for a in managed_assets)),
            "criticality_distribution": dict(Counter(str(a.criticality) for a in managed_assets)),
            "lifecycle_distribution": dict(Counter(str(a.lifecycle_state) for a in managed_assets)),
            "compliance_distribution": dict(
                Counter(str(a.compliance_status) for a in managed_assets)
            ),
            "risk_distribution": dict(
                Counter(_risk_bucket(float(a.risk_score)) for a in managed_assets)
            ),
            "cost_trends": cost_trends,
            "maintenance_trends": maintenance_trends,
            "vendor_performance": await self._vendor_performance(organization_id, managed_assets),
            "computed_at": datetime.now(UTC),
        }

        existing = await self._statistics.get_for_org(organization_id)
        if existing is not None:
            for field, value in snapshot_fields.items():
                setattr(existing, field, value)
            return existing
        return await self._statistics.create(
            AssetStatistics(organization_id=organization_id, **snapshot_fields)
        )


__all__ = ["AssetStatisticsService"]
