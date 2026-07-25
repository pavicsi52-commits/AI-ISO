"""Tests for :class:`app.services.cost.CostService`."""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.enums import CostType
from app.repositories.asset_budget import AssetBudgetRepository
from app.repositories.asset_cost import AssetCostRepository
from app.services.cost import CostService
from tests.conftest import make_managed_asset


def _build(db_session: AsyncSession) -> CostService:
    return CostService(AssetCostRepository(db_session), AssetBudgetRepository(db_session))


async def test_record_cost_and_compute_tco(db_session: AsyncSession) -> None:
    managed_asset = await make_managed_asset(db_session)
    service = _build(db_session)
    now = datetime.now(UTC)

    await service.record_cost(
        managed_asset.id,
        organization_id=managed_asset.organization_id,
        cost_type=CostType.ACQUISITION,
        amount=1000.0,
        currency="USD",
        incurred_at=now,
        description="initial purchase",
    )
    await service.record_cost(
        managed_asset.id,
        organization_id=managed_asset.organization_id,
        cost_type=CostType.MAINTENANCE,
        amount=150.0,
        currency="USD",
        incurred_at=now,
        description="annual service",
    )

    total, by_type, entries = await service.get_total_cost_of_ownership(managed_asset.id)

    assert total == 1150.0
    assert by_type["acquisition"] == 1000.0
    assert by_type["maintenance"] == 150.0
    assert len(entries) == 2


async def test_list_for_managed_asset_filters_by_type(db_session: AsyncSession) -> None:
    managed_asset = await make_managed_asset(db_session)
    service = _build(db_session)
    now = datetime.now(UTC)
    await service.record_cost(
        managed_asset.id,
        organization_id=managed_asset.organization_id,
        cost_type=CostType.CLOUD,
        amount=50.0,
        currency="USD",
        incurred_at=now,
        description=None,
    )
    await service.record_cost(
        managed_asset.id,
        organization_id=managed_asset.organization_id,
        cost_type=CostType.ENERGY,
        amount=20.0,
        currency="USD",
        incurred_at=now,
        description=None,
    )

    cloud_only = await service.list_for_managed_asset(managed_asset.id, cost_type=CostType.CLOUD)
    assert len(cloud_only) == 1
    assert cloud_only[0].cost_type == CostType.CLOUD


async def test_upsert_budget_creates_then_updates(db_session: AsyncSession) -> None:
    managed_asset = await make_managed_asset(db_session)
    service = _build(db_session)

    created = await service.upsert_budget(
        managed_asset.id,
        organization_id=managed_asset.organization_id,
        fiscal_year=2026,
        allocated_amount=5000.0,
        spent_amount=0.0,
        currency="USD",
    )
    updated = await service.upsert_budget(
        managed_asset.id,
        organization_id=managed_asset.organization_id,
        fiscal_year=2026,
        allocated_amount=5000.0,
        spent_amount=1200.0,
        currency="USD",
    )

    assert created.id == updated.id
    assert updated.spent_amount == 1200.0

    budgets = await service.list_budgets(managed_asset.id)
    assert len(budgets) == 1


async def test_tco_with_no_costs_is_zero(db_session: AsyncSession) -> None:
    managed_asset = await make_managed_asset(db_session)
    service = _build(db_session)
    total, by_type, entries = await service.get_total_cost_of_ownership(managed_asset.id)
    assert total == 0.0
    assert by_type == {}
    assert entries == []
