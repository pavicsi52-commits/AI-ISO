"""Tests for :func:`app.workers.sweep_worker.build_sweep_worker`."""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import pytest
from shared_core.exceptions.database import DatabaseError
from sqlalchemy.ext.asyncio import AsyncSession

from app.repositories.asset_contract import AssetContractRepository
from app.repositories.asset_cost import AssetCostRepository
from app.repositories.asset_maintenance import AssetMaintenanceRepository
from app.repositories.asset_statistics import AssetStatisticsRepository
from app.repositories.asset_vendor import AssetVendorRepository
from app.repositories.asset_warranty import AssetWarrantyRepository
from app.repositories.managed_asset import ManagedAssetRepository
from app.services.contract import ContractService
from app.services.statistics import AssetStatisticsService
from app.services.warranty import WarrantyService
from app.workers.sweep_worker import SweepServices, build_sweep_worker
from tests.conftest import make_managed_asset


async def test_sweep_worker_recomputes_statistics(db_session: AsyncSession) -> None:
    org_id = uuid.uuid4()
    await make_managed_asset(db_session, organization_id=org_id)

    @asynccontextmanager
    async def factory() -> AsyncIterator[SweepServices]:
        yield (
            AssetStatisticsService(
                AssetStatisticsRepository(db_session),
                ManagedAssetRepository(db_session),
                AssetCostRepository(db_session),
                AssetMaintenanceRepository(db_session),
                AssetVendorRepository(db_session),
            ),
            WarrantyService(
                AssetWarrantyRepository(db_session), ManagedAssetRepository(db_session)
            ),
            ContractService(AssetContractRepository(db_session), AssetVendorRepository(db_session)),
        )

    handler = build_sweep_worker(factory)
    await handler({"organization_id": str(org_id)})

    snapshot = await AssetStatisticsRepository(db_session).get_for_org(org_id)
    assert snapshot is not None
    assert snapshot.total_managed_assets == 1


async def test_sweep_worker_reraises_on_failure(db_session: AsyncSession) -> None:
    @asynccontextmanager
    async def failing_factory() -> AsyncIterator[SweepServices]:
        raise DatabaseError("boom")
        yield  # pragma: no cover -- unreachable, satisfies generator shape

    handler = build_sweep_worker(failing_factory)
    with pytest.raises(DatabaseError):
        await handler({"organization_id": str(uuid.uuid4())})
