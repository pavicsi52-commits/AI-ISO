"""Tests for :class:`app.services.asset.DiscoveryAssetService` against a
real (SAVEPOINT-isolated) Postgres session, with
:class:`~app.discovery.inventory_sync.InventorySyncClient` mocked (its
own real-HTTP behavior is covered by
``tests/test_discovery_inventory_sync.py``).
"""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock

from shared_core.exceptions.dependency import DependencyError
from sqlalchemy.ext.asyncio import AsyncSession

from app.discovery.inventory_sync import InventorySyncClient
from app.events.discovery_events import AssetDiscoveredEvent, AssetUpdatedEvent
from app.models.enums import AssetClassification, SyncStatus
from app.repositories.discovery_asset import DiscoveryAssetRepository
from app.services.asset import DiscoveryAssetService
from tests.conftest import seed_job, seed_result, seed_target


async def _seed_asset_chain(
    session: AsyncSession, *, organization_id: uuid.UUID
) -> tuple[uuid.UUID, uuid.UUID]:
    job = await seed_job(session, organization_id=organization_id)
    target = await seed_target(session, organization_id=organization_id)
    result = await seed_result(
        session, organization_id=organization_id, job_id=job.id, target_id=target.id
    )
    return job.id, result.id


async def test_record_creates_asset_and_publishes_event(db_session: AsyncSession) -> None:
    org_id = uuid.uuid4()
    job_id, result_id = await _seed_asset_chain(db_session, organization_id=org_id)
    published: list[object] = []

    async def _publish(event: object) -> None:
        published.append(event)

    service = DiscoveryAssetService(
        DiscoveryAssetRepository(db_session),
        AsyncMock(spec=InventorySyncClient),
        publish_event=_publish,
    )
    asset = await service.record(
        job_id,
        result_id,
        organization_id=org_id,
        name="host-1",
        asset_type="server",
        classification=AssetClassification.COMPUTE,
        fingerprint={},
    )
    assert asset.id is not None
    assert len(published) == 1
    assert isinstance(published[0], AssetDiscoveredEvent)


async def test_list_for_job_and_org(db_session: AsyncSession) -> None:
    org_id = uuid.uuid4()
    job_id, result_id = await _seed_asset_chain(db_session, organization_id=org_id)
    service = DiscoveryAssetService(
        DiscoveryAssetRepository(db_session), AsyncMock(spec=InventorySyncClient)
    )
    asset = await service.record(
        job_id,
        result_id,
        organization_id=org_id,
        name="host-1",
        asset_type="server",
        classification=AssetClassification.COMPUTE,
        fingerprint={},
    )

    by_job = await service.list_for_job(job_id)
    assert {record.id for record in by_job} == {asset.id}

    by_org = await service.list_for_org(org_id)
    assert {record.id for record in by_org} == {asset.id}


async def test_sync_to_inventory_created_marks_synced(db_session: AsyncSession) -> None:
    org_id = uuid.uuid4()
    job_id, result_id = await _seed_asset_chain(db_session, organization_id=org_id)
    inventory_asset_id = uuid.uuid4()
    inventory_sync = AsyncMock(spec=InventorySyncClient)
    inventory_sync.sync_asset.return_value = (inventory_asset_id, True)
    service = DiscoveryAssetService(DiscoveryAssetRepository(db_session), inventory_sync)
    asset = await service.record(
        job_id,
        result_id,
        organization_id=org_id,
        name="host-1",
        asset_type="server",
        classification=AssetClassification.COMPUTE,
        fingerprint={},
    )

    synced = await service.sync_to_inventory(
        asset, organization_id=org_id, caller_token="tok", identifiers={}
    )
    assert synced.synced_to_inventory is True
    assert synced.sync_status == SyncStatus.SYNCED
    assert synced.inventory_asset_id == inventory_asset_id


async def test_sync_to_inventory_reconciled_publishes_updated_event(
    db_session: AsyncSession,
) -> None:
    org_id = uuid.uuid4()
    job_id, result_id = await _seed_asset_chain(db_session, organization_id=org_id)
    inventory_sync = AsyncMock(spec=InventorySyncClient)
    inventory_sync.sync_asset.return_value = (uuid.uuid4(), False)
    published: list[object] = []

    async def _publish(event: object) -> None:
        published.append(event)

    service = DiscoveryAssetService(
        DiscoveryAssetRepository(db_session), inventory_sync, publish_event=_publish
    )
    asset = await service.record(
        job_id,
        result_id,
        organization_id=org_id,
        name="host-1",
        asset_type="server",
        classification=AssetClassification.COMPUTE,
        fingerprint={},
    )
    published.clear()

    synced = await service.sync_to_inventory(
        asset, organization_id=org_id, caller_token="tok", identifiers={}
    )
    assert synced.sync_status == SyncStatus.SYNCED
    assert len(published) == 1
    assert isinstance(published[0], AssetUpdatedEvent)


async def test_sync_to_inventory_failure_marks_failed(db_session: AsyncSession) -> None:
    org_id = uuid.uuid4()
    job_id, result_id = await _seed_asset_chain(db_session, organization_id=org_id)
    inventory_sync = AsyncMock(spec=InventorySyncClient)
    inventory_sync.sync_asset.side_effect = DependencyError("unreachable")
    service = DiscoveryAssetService(DiscoveryAssetRepository(db_session), inventory_sync)
    asset = await service.record(
        job_id,
        result_id,
        organization_id=org_id,
        name="host-1",
        asset_type="server",
        classification=AssetClassification.COMPUTE,
        fingerprint={},
    )

    synced = await service.sync_to_inventory(
        asset, organization_id=org_id, caller_token="tok", identifiers={}
    )
    assert synced.sync_status == SyncStatus.FAILED
    assert synced.synced_to_inventory is False
