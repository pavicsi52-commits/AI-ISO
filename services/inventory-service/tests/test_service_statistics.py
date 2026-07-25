"""Tests for :class:`InventoryStatisticsService`."""

from __future__ import annotations

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.asset_relationship import AssetRelationship
from app.models.enums import DiscoverySource, HealthStatus, RelationshipType
from app.repositories.asset import AssetRepository
from app.repositories.asset_discovery_link import AssetDiscoveryLinkRepository
from app.repositories.asset_relationship import AssetRelationshipRepository
from app.repositories.inventory_statistics import InventoryStatisticsRepository
from app.services.discovery_link import AssetDiscoveryLinkService
from app.services.statistics import InventoryStatisticsService
from tests.conftest import make_asset


def _service(db_session: AsyncSession) -> InventoryStatisticsService:
    return InventoryStatisticsService(
        InventoryStatisticsRepository(db_session),
        AssetRepository(db_session),
        AssetRelationshipRepository(db_session),
        AssetDiscoveryLinkRepository(db_session),
    )


async def test_get_for_org_recomputes_when_absent(db_session: AsyncSession) -> None:
    service = _service(db_session)
    org_id = uuid.uuid4()
    await make_asset(db_session, organization_id=org_id, health=HealthStatus.HEALTHY)
    await make_asset(db_session, organization_id=org_id, health=HealthStatus.WARNING)

    snapshot = await service.get_for_org(org_id)
    assert snapshot.total_assets == 2
    assert snapshot.health_distribution == {"healthy": 1, "warning": 1}


async def test_recompute_updates_existing_snapshot(db_session: AsyncSession) -> None:
    service = _service(db_session)
    org_id = uuid.uuid4()
    await make_asset(db_session, organization_id=org_id)
    first = await service.recompute(org_id)
    assert first.total_assets == 1

    await make_asset(db_session, organization_id=org_id)
    second = await service.recompute(org_id)
    assert second.id == first.id
    assert second.total_assets == 2


async def test_recompute_counts_relationships_once_per_edge(db_session: AsyncSession) -> None:
    service = _service(db_session)
    org_id = uuid.uuid4()
    source = await make_asset(db_session, organization_id=org_id, name="source")
    target = await make_asset(db_session, organization_id=org_id, name="target")

    relationships = AssetRelationshipRepository(db_session)
    await relationships.create(
        AssetRelationship(
            organization_id=org_id,
            source_asset_id=source.id,
            target_asset_id=target.id,
            relationship_type=RelationshipType.DEPENDS_ON,
        )
    )

    snapshot = await service.recompute(org_id)
    assert snapshot.total_relationships == 1


async def test_get_analytics_includes_discovery_and_growth(db_session: AsyncSession) -> None:
    service = _service(db_session)
    org_id = uuid.uuid4()
    asset = await make_asset(db_session, organization_id=org_id)

    links = AssetDiscoveryLinkService(AssetDiscoveryLinkRepository(db_session))
    await links.record(
        asset.id, organization_id=org_id, source=DiscoverySource.AGENT, external_id="agent-1"
    )

    analytics = await service.get_analytics(org_id)
    assert analytics["discovery_source_distribution"] == {"agent": 1}
    assert analytics["assets_added_last_30_days"] == 1
    assert analytics["total_assets"] == 1


__all__: list[str] = []
