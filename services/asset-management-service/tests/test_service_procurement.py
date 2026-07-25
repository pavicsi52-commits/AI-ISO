"""Tests for :class:`app.services.procurement.ProcurementService`."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.enums import DepreciationMethod
from app.repositories.asset_depreciation import AssetDepreciationRepository
from app.repositories.asset_procurement import AssetProcurementRepository
from app.services.procurement import ProcurementService
from tests.conftest import make_managed_asset


def _build(db_session: AsyncSession) -> ProcurementService:
    return ProcurementService(
        AssetProcurementRepository(db_session), AssetDepreciationRepository(db_session)
    )


async def test_upsert_procurement_creates_then_updates(db_session: AsyncSession) -> None:
    managed_asset = await make_managed_asset(db_session)
    service = _build(db_session)

    created = await service.upsert_procurement(
        managed_asset.id,
        organization_id=managed_asset.organization_id,
        vendor_id=None,
        purchase_order_number="PO-1",
        invoice_number=None,
        cost_center=None,
        acquisition_cost=1000.0,
        purchase_date=None,
        expected_lifetime_months=36,
        financial_metadata={},
    )
    updated = await service.upsert_procurement(
        managed_asset.id,
        organization_id=managed_asset.organization_id,
        vendor_id=None,
        purchase_order_number="PO-2",
        invoice_number=None,
        cost_center=None,
        acquisition_cost=1200.0,
        purchase_date=None,
        expected_lifetime_months=36,
        financial_metadata={},
    )

    assert created.id == updated.id
    assert updated.purchase_order_number == "PO-2"
    assert updated.acquisition_cost == 1200.0


async def test_upsert_depreciation_computes_book_value(db_session: AsyncSession) -> None:
    managed_asset = await make_managed_asset(db_session)
    service = _build(db_session)
    acquired_at = datetime.now(UTC) - timedelta(days=365)

    depreciation = await service.upsert_depreciation(
        managed_asset.id,
        organization_id=managed_asset.organization_id,
        method=DepreciationMethod.STRAIGHT_LINE,
        acquisition_cost=1200.0,
        residual_value=200.0,
        useful_life_months=24,
        acquired_at=acquired_at,
    )

    # Roughly half the useful life has elapsed (12/24 months): book value
    # should sit between the residual and full acquisition cost.
    assert 200.0 < depreciation.book_value < 1200.0
    assert depreciation.last_computed_at is not None


async def test_upsert_depreciation_twice_updates_same_row(db_session: AsyncSession) -> None:
    managed_asset = await make_managed_asset(db_session)
    service = _build(db_session)
    acquired_at = datetime.now(UTC) - timedelta(days=30)

    first = await service.upsert_depreciation(
        managed_asset.id,
        organization_id=managed_asset.organization_id,
        method=DepreciationMethod.STRAIGHT_LINE,
        acquisition_cost=1200.0,
        residual_value=200.0,
        useful_life_months=24,
        acquired_at=acquired_at,
    )
    second = await service.upsert_depreciation(
        managed_asset.id,
        organization_id=managed_asset.organization_id,
        method=DepreciationMethod.DECLINING_BALANCE,
        acquisition_cost=1500.0,
        residual_value=300.0,
        useful_life_months=36,
        acquired_at=acquired_at,
    )

    assert first.id == second.id
    assert second.method == DepreciationMethod.DECLINING_BALANCE
    assert second.acquisition_cost == 1500.0


async def test_upsert_depreciation_zero_useful_life_returns_full_cost(
    db_session: AsyncSession,
) -> None:
    managed_asset = await make_managed_asset(db_session)
    service = _build(db_session)

    depreciation = await service.upsert_depreciation(
        managed_asset.id,
        organization_id=managed_asset.organization_id,
        method=DepreciationMethod.CUSTOM,
        acquisition_cost=500.0,
        residual_value=0.0,
        useful_life_months=0,
        acquired_at=datetime.now(UTC),
    )

    assert depreciation.book_value == 500.0


async def test_get_procurement_returns_none_when_absent(db_session: AsyncSession) -> None:
    managed_asset = await make_managed_asset(db_session)
    service = _build(db_session)
    assert await service.get_procurement(managed_asset.id) is None
    assert await service.get_depreciation(managed_asset.id) is None
