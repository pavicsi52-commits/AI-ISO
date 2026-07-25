"""Tests for :class:`app.services.statistics.DiscoveryStatisticsService`
against a real (SAVEPOINT-isolated) Postgres session.
"""

from __future__ import annotations

import uuid
from unittest.mock import MagicMock

from sqlalchemy.ext.asyncio import AsyncSession

from app.discovery.inventory_sync import InventorySyncClient
from app.models.enums import DiscoveryRelationshipType, FailureReason, ProtocolType
from app.repositories.discovery_asset import DiscoveryAssetRepository
from app.repositories.discovery_failure import DiscoveryFailureRepository
from app.repositories.discovery_job import DiscoveryJobRepository
from app.repositories.discovery_relationship import DiscoveryRelationshipRepository
from app.repositories.discovery_statistics import DiscoveryStatisticsRepository
from app.services.failure import DiscoveryFailureService
from app.services.relationship import DiscoveryRelationshipService
from app.services.statistics import DiscoveryStatisticsService
from tests.conftest import seed_asset, seed_job, seed_result, seed_target


def _service(session: AsyncSession) -> DiscoveryStatisticsService:
    return DiscoveryStatisticsService(
        DiscoveryStatisticsRepository(session),
        DiscoveryJobRepository(session),
        DiscoveryAssetRepository(session),
        DiscoveryRelationshipRepository(session),
        DiscoveryFailureRepository(session),
    )


async def test_get_for_org_with_no_activity_returns_zeroed_snapshot(
    db_session: AsyncSession,
) -> None:
    service = _service(db_session)
    org_id = uuid.uuid4()
    snapshot = await service.get_for_org(org_id)
    assert snapshot.total_jobs == 0
    assert snapshot.total_assets_discovered == 0
    assert snapshot.total_relationships_discovered == 0
    assert snapshot.last_discovery_at is None


async def test_recompute_aggregates_jobs_assets_relationships_and_failures(
    db_session: AsyncSession,
) -> None:
    org_id = uuid.uuid4()
    job = await seed_job(db_session, organization_id=org_id)
    target = await seed_target(db_session, organization_id=org_id)
    result = await seed_result(
        db_session, organization_id=org_id, job_id=job.id, target_id=target.id
    )
    asset_a = await seed_asset(
        db_session, organization_id=org_id, job_id=job.id, result_id=result.id, name="a"
    )
    asset_b = await seed_asset(
        db_session, organization_id=org_id, job_id=job.id, result_id=result.id, name="b"
    )

    relationships = DiscoveryRelationshipService(
        DiscoveryRelationshipRepository(db_session), MagicMock(spec=InventorySyncClient)
    )
    await relationships.record(
        job.id,
        organization_id=org_id,
        source_discovery_asset_id=asset_a.id,
        target_discovery_asset_id=asset_b.id,
        relationship_type=DiscoveryRelationshipType.CONNECTED_TO,
    )

    failures = DiscoveryFailureService(DiscoveryFailureRepository(db_session))
    await failures.record(
        job.id,
        organization_id=org_id,
        target_id=target.id,
        protocol=ProtocolType.TCP,
        failure_reason=FailureReason.TIMEOUT,
    )

    service = _service(db_session)
    snapshot = await service.recompute(org_id)
    assert snapshot.total_jobs == 1
    assert snapshot.total_assets_discovered == 2
    assert snapshot.total_relationships_discovered == 1
    assert snapshot.failures_by_reason == {"timeout": 1}
    assert snapshot.last_discovery_at is None


async def test_recompute_updates_existing_snapshot_in_place(db_session: AsyncSession) -> None:
    org_id = uuid.uuid4()
    service = _service(db_session)
    first = await service.recompute(org_id)

    await seed_job(db_session, organization_id=org_id)
    second = await service.recompute(org_id)

    assert second.id == first.id
    assert second.total_jobs == 1


async def test_get_for_org_returns_cached_snapshot_without_recomputing(
    db_session: AsyncSession,
) -> None:
    org_id = uuid.uuid4()
    service = _service(db_session)
    await service.recompute(org_id)

    await seed_job(db_session, organization_id=org_id)
    cached = await service.get_for_org(org_id)
    assert cached.total_jobs == 0
