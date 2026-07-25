"""Tests for :class:`app.services.statistics.AssetStatisticsService`."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.asset_cost import AssetCost
from app.models.asset_maintenance import AssetMaintenance
from app.models.asset_vendor import AssetVendor
from app.models.enums import (
    CostType,
    Criticality,
    MaintenanceStatus,
    MaintenanceType,
    ManagedAssetStatus,
)
from app.repositories.asset_cost import AssetCostRepository
from app.repositories.asset_maintenance import AssetMaintenanceRepository
from app.repositories.asset_statistics import AssetStatisticsRepository
from app.repositories.asset_vendor import AssetVendorRepository
from app.repositories.managed_asset import ManagedAssetRepository
from app.services.statistics import AssetStatisticsService
from tests.conftest import make_managed_asset


def _build(db_session: AsyncSession) -> AssetStatisticsService:
    return AssetStatisticsService(
        AssetStatisticsRepository(db_session),
        ManagedAssetRepository(db_session),
        AssetCostRepository(db_session),
        AssetMaintenanceRepository(db_session),
        AssetVendorRepository(db_session),
    )


async def test_get_for_org_recomputes_when_missing(db_session: AsyncSession) -> None:
    org_id = uuid.uuid4()
    await make_managed_asset(
        db_session, organization_id=org_id, status=ManagedAssetStatus.OPERATIONAL
    )
    await make_managed_asset(
        db_session,
        organization_id=org_id,
        status=ManagedAssetStatus.OPERATIONAL,
        criticality=Criticality.CRITICAL,
    )

    service = _build(db_session)
    snapshot = await service.get_for_org(org_id)

    assert snapshot.total_managed_assets == 2
    assert snapshot.status_distribution["operational"] == 2
    assert snapshot.criticality_distribution["critical"] == 1


async def test_recompute_includes_cost_trends(db_session: AsyncSession) -> None:
    org_id = uuid.uuid4()
    managed_asset = await make_managed_asset(db_session, organization_id=org_id)

    costs = AssetCostRepository(db_session)
    await costs.create(
        AssetCost(
            managed_asset_id=managed_asset.id,
            organization_id=org_id,
            cost_type=CostType.CLOUD,
            amount=250.0,
            currency="USD",
            incurred_at=datetime.now(UTC),
        )
    )

    service = _build(db_session)
    snapshot = await service.recompute(org_id)

    assert snapshot.cost_trends["cloud"] == 250.0


async def test_recompute_twice_updates_existing_row(db_session: AsyncSession) -> None:
    org_id = uuid.uuid4()
    await make_managed_asset(db_session, organization_id=org_id)
    service = _build(db_session)

    first = await service.recompute(org_id)
    await make_managed_asset(db_session, organization_id=org_id)
    second = await service.recompute(org_id)

    assert first.id == second.id
    assert second.total_managed_assets == 2


async def test_get_for_org_returns_cached_snapshot_without_recomputing(
    db_session: AsyncSession,
) -> None:
    org_id = uuid.uuid4()
    await make_managed_asset(db_session, organization_id=org_id)
    service = _build(db_session)
    cached = await service.get_for_org(org_id)

    # A second managed asset created after the first snapshot must NOT
    # be reflected by a cache-hit ``get_for_org`` call.
    await make_managed_asset(db_session, organization_id=org_id)
    again = await service.get_for_org(org_id)

    assert again.id == cached.id
    assert again.total_managed_assets == 1


async def test_recompute_risk_distribution_buckets(db_session: AsyncSession) -> None:
    org_id = uuid.uuid4()
    for score in (5.0, 30.0, 55.0, 80.0):
        managed_asset = await make_managed_asset(db_session, organization_id=org_id)
        managed_asset.risk_score = score
    await db_session.flush()

    service = _build(db_session)
    snapshot = await service.recompute(org_id)

    assert snapshot.risk_distribution == {
        "low": 1,
        "medium": 1,
        "high": 1,
        "critical": 1,
    }


async def test_recompute_maintenance_trends_and_vendor_performance(
    db_session: AsyncSession,
) -> None:
    org_id = uuid.uuid4()
    vendor = AssetVendor(organization_id=org_id, name="Acme Corp")
    db_session.add(vendor)
    await db_session.flush()

    managed_asset = await make_managed_asset(db_session, organization_id=org_id)
    managed_asset.vendor_id = vendor.id
    db_session.add(
        AssetMaintenance(
            managed_asset_id=managed_asset.id,
            organization_id=org_id,
            maintenance_type=MaintenanceType.PREVENTIVE,
            status=MaintenanceStatus.SCHEDULED,
            description="Checkup",
            scheduled_at=datetime.now(UTC),
        )
    )
    await db_session.flush()

    service = _build(db_session)
    snapshot = await service.recompute(org_id)

    assert snapshot.maintenance_trends["scheduled"] == 1
    assert snapshot.vendor_performance["Acme Corp"] == 1
