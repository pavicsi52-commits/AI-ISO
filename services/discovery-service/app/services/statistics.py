"""Discovery statistics/analytics computation. Computed on demand and
cached, the same "cached, not live" shape
``services/inventory-service``'s own ``InventoryStatisticsService``
established.
"""

from __future__ import annotations

from collections import Counter
from datetime import UTC, datetime
from uuid import UUID

from app.models.discovery_statistics import DiscoveryStatistics
from app.repositories.discovery_asset import DiscoveryAssetRepository
from app.repositories.discovery_failure import DiscoveryFailureRepository
from app.repositories.discovery_job import DiscoveryJobRepository
from app.repositories.discovery_relationship import DiscoveryRelationshipRepository
from app.repositories.discovery_statistics import DiscoveryStatisticsRepository


class DiscoveryStatisticsService:
    """Recomputes and reads an organization's cached discovery analytics."""

    def __init__(
        self,
        statistics: DiscoveryStatisticsRepository,
        jobs: DiscoveryJobRepository,
        assets: DiscoveryAssetRepository,
        relationships: DiscoveryRelationshipRepository,
        failures: DiscoveryFailureRepository,
    ) -> None:
        self._statistics = statistics
        self._jobs = jobs
        self._assets = assets
        self._relationships = relationships
        self._failures = failures

    async def get_for_org(self, organization_id: UUID) -> DiscoveryStatistics:
        """Return *organization_id*'s cached snapshot, recomputing if none exists yet."""
        existing = await self._statistics.get_for_org(organization_id)
        if existing is not None:
            return existing
        return await self.recompute(organization_id)

    async def recompute(self, organization_id: UUID) -> DiscoveryStatistics:
        """Recompute and persist *organization_id*'s statistics snapshot."""
        jobs = await self._jobs.list_for_org(organization_id)
        assets = await self._assets.list_for_org(organization_id)

        jobs_by_mode = Counter(str(job.mode) for job in jobs)
        assets_by_classification = Counter(str(asset.classification) for asset in assets)

        relationship_count = 0
        seen_relationship_ids: set[UUID] = set()
        failures_by_reason: Counter[str] = Counter()
        for job in jobs:
            for relationship in await self._relationships.list_for_job(job.id):
                if relationship.id not in seen_relationship_ids:
                    seen_relationship_ids.add(relationship.id)
                    relationship_count += 1
            for failure in await self._failures.list_for_job(job.id):
                failures_by_reason[str(failure.failure_reason)] += 1

        last_discovery_at = max(
            (job.completed_at for job in jobs if job.completed_at), default=None
        )

        existing = await self._statistics.get_for_org(organization_id)
        snapshot = DiscoveryStatistics(
            organization_id=organization_id,
            total_jobs=len(jobs),
            total_assets_discovered=len(assets),
            total_relationships_discovered=relationship_count,
            jobs_by_mode=dict(jobs_by_mode),
            assets_by_classification=dict(assets_by_classification),
            failures_by_reason=dict(failures_by_reason),
            last_discovery_at=last_discovery_at,
            computed_at=datetime.now(UTC),
        )
        if existing is not None:
            existing.total_jobs = snapshot.total_jobs
            existing.total_assets_discovered = snapshot.total_assets_discovered
            existing.total_relationships_discovered = snapshot.total_relationships_discovered
            existing.jobs_by_mode = snapshot.jobs_by_mode
            existing.assets_by_classification = snapshot.assets_by_classification
            existing.failures_by_reason = snapshot.failures_by_reason
            existing.last_discovery_at = snapshot.last_discovery_at
            existing.computed_at = snapshot.computed_at
            return existing
        return await self._statistics.create(snapshot)


__all__ = ["DiscoveryStatisticsService"]
