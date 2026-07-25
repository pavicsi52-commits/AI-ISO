"""Tests for :class:`app.services.health.HealthService`."""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.enums import OperationalHealth
from app.repositories.asset_health_rollup import AssetHealthRollupRepository
from app.repositories.managed_asset import ManagedAssetRepository
from app.services.health import HealthService
from tests.conftest import make_managed_asset


def _build(db_session: AsyncSession) -> HealthService:
    return HealthService(
        AssetHealthRollupRepository(db_session), ManagedAssetRepository(db_session)
    )


async def test_recompute_creates_rollup_and_sets_healthy(db_session: AsyncSession) -> None:
    managed_asset = await make_managed_asset(db_session)
    service = _build(db_session)

    rollup = await service.recompute(
        managed_asset.id,
        organization_id=managed_asset.organization_id,
        monitoring_status="active",
        validation_status="passed",
        discovery_status="discovered",
        automation_status="enabled",
        incident_count=0,
        performance_indicators={"cpu": 12.5},
        availability_percent=99.9,
        health_score=95.0,
    )

    assert rollup.health_score == 95.0
    assert managed_asset.operational_health == OperationalHealth.HEALTHY
    assert len(rollup.health_trend) == 1


async def test_recompute_sets_critical_below_threshold(db_session: AsyncSession) -> None:
    managed_asset = await make_managed_asset(db_session)
    service = _build(db_session)

    await service.recompute(
        managed_asset.id,
        organization_id=managed_asset.organization_id,
        monitoring_status="degraded",
        validation_status="failed",
        discovery_status="discovered",
        automation_status="disabled",
        incident_count=5,
        performance_indicators={},
        availability_percent=60.0,
        health_score=20.0,
    )

    assert managed_asset.operational_health == OperationalHealth.CRITICAL


async def test_recompute_sets_warning_between_thresholds(db_session: AsyncSession) -> None:
    managed_asset = await make_managed_asset(db_session)
    service = _build(db_session)

    await service.recompute(
        managed_asset.id,
        organization_id=managed_asset.organization_id,
        monitoring_status="active",
        validation_status="passed",
        discovery_status="discovered",
        automation_status="enabled",
        incident_count=1,
        performance_indicators={},
        availability_percent=85.0,
        health_score=55.0,
    )

    assert managed_asset.operational_health == OperationalHealth.WARNING


async def test_recompute_twice_appends_trend(db_session: AsyncSession) -> None:
    managed_asset = await make_managed_asset(db_session)
    service = _build(db_session)
    await service.recompute(
        managed_asset.id,
        organization_id=managed_asset.organization_id,
        monitoring_status="active",
        validation_status="passed",
        discovery_status="discovered",
        automation_status="enabled",
        incident_count=0,
        performance_indicators={},
        availability_percent=99.0,
        health_score=90.0,
    )
    updated = await service.recompute(
        managed_asset.id,
        organization_id=managed_asset.organization_id,
        monitoring_status="active",
        validation_status="passed",
        discovery_status="discovered",
        automation_status="enabled",
        incident_count=0,
        performance_indicators={},
        availability_percent=98.0,
        health_score=88.0,
    )

    assert len(updated.health_trend) == 2


async def test_get_for_managed_asset_returns_none_when_absent(db_session: AsyncSession) -> None:
    managed_asset = await make_managed_asset(db_session)
    service = _build(db_session)
    assert await service.get_for_managed_asset(managed_asset.id) is None
