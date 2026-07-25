"""Tests for :class:`app.services.relationship.DiscoveryRelationshipService`
against a real (SAVEPOINT-isolated) Postgres session, with
:class:`~app.discovery.inventory_sync.InventorySyncClient` mocked.
"""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock

from shared_core.exceptions.dependency import DependencyError
from sqlalchemy.ext.asyncio import AsyncSession

from app.discovery.inventory_sync import InventorySyncClient
from app.events.discovery_events import RelationshipDiscoveredEvent
from app.models.discovery_asset import DiscoveryAsset
from app.models.enums import AssetClassification, DiscoveryRelationshipType
from app.repositories.discovery_asset import DiscoveryAssetRepository
from app.repositories.discovery_relationship import DiscoveryRelationshipRepository
from app.services.asset import DiscoveryAssetService
from app.services.relationship import DiscoveryRelationshipService
from tests.conftest import seed_job, seed_result, seed_target


async def _seed_two_assets(
    session: AsyncSession, *, organization_id: uuid.UUID
) -> tuple[uuid.UUID, DiscoveryAsset, DiscoveryAsset]:
    job = await seed_job(session, organization_id=organization_id)
    target = await seed_target(session, organization_id=organization_id)
    result = await seed_result(
        session, organization_id=organization_id, job_id=job.id, target_id=target.id
    )
    assets = DiscoveryAssetService(
        DiscoveryAssetRepository(session), AsyncMock(spec=InventorySyncClient)
    )
    source = await assets.record(
        job.id,
        result.id,
        organization_id=organization_id,
        name="source",
        asset_type="host",
        classification=AssetClassification.COMPUTE,
        fingerprint={},
    )
    target_asset = await assets.record(
        job.id,
        result.id,
        organization_id=organization_id,
        name="target",
        asset_type="host",
        classification=AssetClassification.COMPUTE,
        fingerprint={},
    )
    return job.id, source, target_asset


async def test_record_creates_relationship_and_publishes_event(db_session: AsyncSession) -> None:
    org_id = uuid.uuid4()
    job_id, source, target = await _seed_two_assets(db_session, organization_id=org_id)
    published: list[object] = []

    async def _publish(event: object) -> None:
        published.append(event)

    service = DiscoveryRelationshipService(
        DiscoveryRelationshipRepository(db_session),
        AsyncMock(spec=InventorySyncClient),
        publish_event=_publish,
    )
    relationship = await service.record(
        job_id,
        organization_id=org_id,
        source_discovery_asset_id=source.id,
        target_discovery_asset_id=target.id,
        relationship_type=DiscoveryRelationshipType.CONNECTED_TO,
    )
    assert relationship.id is not None
    assert len(published) == 1
    assert isinstance(published[0], RelationshipDiscoveredEvent)


async def test_list_for_job_and_get_by_edge(db_session: AsyncSession) -> None:
    org_id = uuid.uuid4()
    job_id, source, target = await _seed_two_assets(db_session, organization_id=org_id)
    service = DiscoveryRelationshipService(
        DiscoveryRelationshipRepository(db_session), AsyncMock(spec=InventorySyncClient)
    )
    relationship = await service.record(
        job_id,
        organization_id=org_id,
        source_discovery_asset_id=source.id,
        target_discovery_asset_id=target.id,
        relationship_type=DiscoveryRelationshipType.CONNECTED_TO,
    )

    by_job = await service.list_for_job(job_id)
    assert {record.id for record in by_job} == {relationship.id}

    found = await service.get_by_edge(source.id, target.id, DiscoveryRelationshipType.CONNECTED_TO)
    assert found is not None
    assert found.id == relationship.id

    missing = await service.get_by_edge(
        target.id, source.id, DiscoveryRelationshipType.CONNECTED_TO
    )
    assert missing is None


async def test_sync_to_inventory_skips_when_endpoints_unsynced(db_session: AsyncSession) -> None:
    org_id = uuid.uuid4()
    job_id, source, target = await _seed_two_assets(db_session, organization_id=org_id)
    inventory_sync = AsyncMock(spec=InventorySyncClient)
    service = DiscoveryRelationshipService(
        DiscoveryRelationshipRepository(db_session), inventory_sync
    )
    relationship = await service.record(
        job_id,
        organization_id=org_id,
        source_discovery_asset_id=source.id,
        target_discovery_asset_id=target.id,
        relationship_type=DiscoveryRelationshipType.CONNECTED_TO,
    )

    result = await service.sync_to_inventory(
        relationship,
        organization_id=org_id,
        source_asset=source,
        target_asset=target,
        caller_token="tok",
    )
    assert result.synced_to_inventory is False
    inventory_sync.sync_relationship.assert_not_awaited()


async def test_sync_to_inventory_succeeds_when_endpoints_synced(db_session: AsyncSession) -> None:
    org_id = uuid.uuid4()
    job_id, source, target = await _seed_two_assets(db_session, organization_id=org_id)
    source.inventory_asset_id = uuid.uuid4()
    target.inventory_asset_id = uuid.uuid4()
    inventory_sync = AsyncMock(spec=InventorySyncClient)
    service = DiscoveryRelationshipService(
        DiscoveryRelationshipRepository(db_session), inventory_sync
    )
    relationship = await service.record(
        job_id,
        organization_id=org_id,
        source_discovery_asset_id=source.id,
        target_discovery_asset_id=target.id,
        relationship_type=DiscoveryRelationshipType.CONNECTED_TO,
    )

    result = await service.sync_to_inventory(
        relationship,
        organization_id=org_id,
        source_asset=source,
        target_asset=target,
        caller_token="tok",
    )
    assert result.synced_to_inventory is True
    inventory_sync.sync_relationship.assert_awaited_once()


async def test_sync_to_inventory_failure_leaves_unsynced(db_session: AsyncSession) -> None:
    org_id = uuid.uuid4()
    job_id, source, target = await _seed_two_assets(db_session, organization_id=org_id)
    source.inventory_asset_id = uuid.uuid4()
    target.inventory_asset_id = uuid.uuid4()
    inventory_sync = AsyncMock(spec=InventorySyncClient)
    inventory_sync.sync_relationship.side_effect = DependencyError("unreachable")
    service = DiscoveryRelationshipService(
        DiscoveryRelationshipRepository(db_session), inventory_sync
    )
    relationship = await service.record(
        job_id,
        organization_id=org_id,
        source_discovery_asset_id=source.id,
        target_discovery_asset_id=target.id,
        relationship_type=DiscoveryRelationshipType.CONNECTED_TO,
    )

    result = await service.sync_to_inventory(
        relationship,
        organization_id=org_id,
        source_asset=source,
        target_asset=target,
        caller_token="tok",
    )
    assert result.synced_to_inventory is False
