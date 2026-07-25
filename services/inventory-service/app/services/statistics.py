"""Inventory statistics/analytics computation. Per docs/036
"ANALYTICS": Asset Count, Asset Types, Health Distribution, Lifecycle
Distribution, OS Distribution, Vendor Distribution, Location
Distribution, Relationship Count, Discovery Statistics, Growth Trends.
Computed on demand and cached, the same "cached, not live" shape
``services/project-service``'s own ``project_statistics`` established.
"""

from __future__ import annotations

from collections import Counter
from datetime import UTC, datetime, timedelta
from uuid import UUID

from app.models.inventory_statistics import InventoryStatistics
from app.repositories.asset import AssetRepository
from app.repositories.asset_discovery_link import AssetDiscoveryLinkRepository
from app.repositories.asset_relationship import AssetRelationshipRepository
from app.repositories.inventory_statistics import InventoryStatisticsRepository

_GROWTH_WINDOW = timedelta(days=30)


class InventoryStatisticsService:
    """Recomputes and reads an organization's cached inventory analytics."""

    def __init__(
        self,
        statistics: InventoryStatisticsRepository,
        assets: AssetRepository,
        relationships: AssetRelationshipRepository,
        discovery_links: AssetDiscoveryLinkRepository,
    ) -> None:
        self._statistics = statistics
        self._assets = assets
        self._relationships = relationships
        self._discovery_links = discovery_links

    async def get_for_org(self, organization_id: UUID) -> InventoryStatistics:
        """Return *organization_id*'s cached snapshot, recomputing if none exists yet."""
        existing = await self._statistics.get_for_org(organization_id)
        if existing is not None:
            return existing
        return await self.recompute(organization_id)

    async def recompute(self, organization_id: UUID) -> InventoryStatistics:
        """Recompute and persist *organization_id*'s statistics snapshot."""
        assets = await self._assets.list_for_org(organization_id)
        relationship_count = 0
        seen_relationship_ids: set[UUID] = set()
        for asset in assets:
            for relationship in await self._relationships.list_for_asset(asset.id):
                if relationship.id not in seen_relationship_ids:
                    seen_relationship_ids.add(relationship.id)
                    relationship_count += 1

        type_distribution = Counter(str(asset.asset_type) for asset in assets)
        health_distribution = Counter(str(asset.health) for asset in assets)
        lifecycle_distribution = Counter(str(asset.lifecycle_state) for asset in assets)
        os_distribution = Counter(asset.operating_system or "unknown" for asset in assets)
        vendor_distribution = Counter(asset.vendor or "unknown" for asset in assets)
        location_distribution = Counter(
            str(asset.location_id) if asset.location_id else "unassigned" for asset in assets
        )

        existing = await self._statistics.get_for_org(organization_id)
        snapshot = InventoryStatistics(
            organization_id=organization_id,
            total_assets=len(assets),
            total_relationships=relationship_count,
            type_distribution=dict(type_distribution),
            health_distribution=dict(health_distribution),
            lifecycle_distribution=dict(lifecycle_distribution),
            os_distribution=dict(os_distribution),
            vendor_distribution=dict(vendor_distribution),
            location_distribution=dict(location_distribution),
            computed_at=datetime.now(UTC),
        )
        if existing is not None:
            existing.total_assets = snapshot.total_assets
            existing.total_relationships = snapshot.total_relationships
            existing.type_distribution = snapshot.type_distribution
            existing.health_distribution = snapshot.health_distribution
            existing.lifecycle_distribution = snapshot.lifecycle_distribution
            existing.os_distribution = snapshot.os_distribution
            existing.vendor_distribution = snapshot.vendor_distribution
            existing.location_distribution = snapshot.location_distribution
            existing.computed_at = snapshot.computed_at
            return existing
        return await self._statistics.create(snapshot)

    async def get_analytics(self, organization_id: UUID) -> dict[str, object]:
        """The statistics snapshot plus discovery-source distribution and
        30-day growth trend ("Discovery Statistics", "Growth Trends").
        """
        snapshot = await self.get_for_org(organization_id)
        assets = await self._assets.list_for_org(organization_id)
        cutoff = datetime.now(UTC) - _GROWTH_WINDOW
        added_recently = sum(1 for asset in assets if asset.created_at >= cutoff)

        discovery_sources: Counter[str] = Counter()
        for asset in assets:
            for link in await self._discovery_links.list_for_asset(asset.id):
                discovery_sources[str(link.source)] += 1

        return {
            "total_assets": snapshot.total_assets,
            "total_relationships": snapshot.total_relationships,
            "type_distribution": snapshot.type_distribution,
            "health_distribution": snapshot.health_distribution,
            "lifecycle_distribution": snapshot.lifecycle_distribution,
            "os_distribution": snapshot.os_distribution,
            "vendor_distribution": snapshot.vendor_distribution,
            "location_distribution": snapshot.location_distribution,
            "computed_at": snapshot.computed_at,
            "discovery_source_distribution": dict(discovery_sources),
            "assets_added_last_30_days": added_recently,
        }


__all__ = ["InventoryStatisticsService"]
